from datetime import date
from decimal import Decimal, localcontext
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierComparison,
)
from procurement.services import (
    approve_purchase_order,
    create_alternative_request,
    create_purchase_order,
    create_supplier_comparison,
    mark_purchase_order_sent,
    record_expected_delivery,
)
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class ProcurementOrderServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)

    def item_data(self, **overrides):
        return {
            "nomenclature_id": self.request_item.nomenclature_id,
            "quantity": Decimal("2.000000"),
            "unit_price": Decimal("10.1234"),
            "expected_date": date(2026, 10, 10),
        } | overrides

    def create_order(self, **overrides):
        data = {
            "project_id": self.purchase_request.project_id,
            "supplier": self.supplier,
            "number": "PO-001",
            "currency_code": "KZT",
            "items": [self.item_data()],
        }
        return create_purchase_order(**(data | overrides))

    def alternative_data(self, **overrides):
        return {
            "project_id": self.purchase_request.project_id,
            "request_item": self.request_item,
            "original_nomenclature_id": self.request_item.nomenclature_id,
            "alternative_nomenclature_id": uuid4(),
        } | overrides

    def test_create_comparison_and_default_json_fields(self):
        comparison = create_supplier_comparison(
            self.purchase_request,
            version=1,
            criteria={"weights": {"price": 70, "delivery": 30}},
            result={"selected_supplier_id": str(self.supplier.pk)},
        )
        comparison.refresh_from_db()
        self.assertEqual(comparison.criteria["weights"]["price"], 70)
        self.assertEqual(comparison.result["selected_supplier_id"], str(self.supplier.pk))
        next_version = create_supplier_comparison(self.purchase_request, version=2)
        self.assertEqual(next_version.criteria, {})
        self.assertEqual(next_version.result, {})

    def test_duplicate_and_nonpositive_comparison_versions_are_rejected(self):
        create_supplier_comparison(self.purchase_request, version=1)
        for version in (1, 0, -1):
            with self.subTest(version=version):
                with self.assertRaises(ValidationError):
                    create_supplier_comparison(self.purchase_request, version=version)
        self.assertEqual(SupplierComparison.objects.count(), 1)

    def test_create_order_with_items_and_calculate_total(self):
        order = self.create_order(items=[
            self.item_data(),
            self.item_data(quantity=Decimal("0.5"), unit_price=Decimal("3")),
        ])
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("21.7468"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.status, PurchaseOrder.Status.DRAFT)
        self.assertIsNone(order.approved_at)
        self.assertIsNone(order.sent_at)

    def test_total_rounds_once_after_summing_products(self):
        line = self.item_data(quantity=Decimal("0.5"), unit_price=Decimal("0.0001"))
        order = self.create_order(items=[line, line])
        self.assertEqual(order.total_amount, Decimal("0.0001"))
        half_up = self.create_order(number="PO-002", items=[line])
        self.assertEqual(half_up.total_amount, Decimal("0.0001"))

    def test_calculation_does_not_depend_on_callers_decimal_precision(self):
        with localcontext() as decimal_context:
            decimal_context.prec = 4
            order = self.create_order()
        self.assertEqual(order.total_amount, Decimal("20.2468"))

    def test_total_overflow_rolls_back_order_and_items(self):
        with self.assertRaises(ValidationError):
            self.create_order(items=[self.item_data(
                quantity=Decimal("99999999999999.999999"),
                unit_price=Decimal("9999999999999999.9999"),
            )])
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(PurchaseOrderItem.objects.exists())

    def test_empty_order_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.create_order(items=[])
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_invalid_later_item_rolls_back_order_items_and_event(self):
        for field, value in (
            ("quantity", Decimal("-0.000001")),
            ("unit_price", Decimal("-0.0001")),
        ):
            with self.subTest(field=field):
                with self.captureOnCommitCallbacks(execute=False) as callbacks:
                    with self.assertRaises(ValidationError):
                        self.create_order(items=[
                            self.item_data(), self.item_data(**{field: value})
                        ])
                self.assertEqual(callbacks, [])
                self.assertFalse(PurchaseOrder.objects.exists())
                self.assertFalse(PurchaseOrderItem.objects.exists())

    def test_duplicate_order_number_and_invalid_currency_are_rejected(self):
        self.create_order()
        with self.assertRaises(ValidationError):
            self.create_order()
        for currency in ("KZ", "kzt"):
            with self.subTest(currency=currency):
                with self.assertRaises(ValidationError):
                    self.create_order(number="PO-002", currency_code=currency)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_approve_order_sets_aware_timestamp(self):
        order = approve_purchase_order(self.create_order())
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.APPROVED)
        self.assertTrue(timezone.is_aware(order.approved_at))
        self.assertIsNone(order.sent_at)

    def test_repeated_approve_uses_current_state_even_with_stale_instance(self):
        stale_order = self.create_order()
        approved = approve_purchase_order(stale_order)
        approved_at = approved.approved_at
        with self.assertRaises(ValidationError):
            approve_purchase_order(stale_order)
        approved.refresh_from_db()
        self.assertEqual(approved.status, PurchaseOrder.Status.APPROVED)
        self.assertEqual(approved.approved_at, approved_at)

    def test_cancelled_and_empty_orders_cannot_be_approved(self):
        cancelled = self.create_order()
        PurchaseOrder.objects.filter(pk=cancelled.pk).update(status=PurchaseOrder.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            approve_purchase_order(cancelled)
        empty = PurchaseOrder.objects.create(
            project_id=self.purchase_request.project_id,
            supplier=self.supplier,
            number="PO-EMPTY",
            currency_code="KZT",
        )
        with self.assertRaises(ValidationError):
            approve_purchase_order(empty)

    def test_send_before_approve_is_rejected(self):
        order = self.create_order()
        with self.assertRaises(ValidationError):
            mark_purchase_order_sent(order)
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.DRAFT)
        self.assertIsNone(order.sent_at)

    def test_send_after_approve_sets_timestamp_and_repeated_send_is_rejected(self):
        stale_order = self.create_order()
        approved = approve_purchase_order(stale_order)
        sent = mark_purchase_order_sent(stale_order)
        sent_at = sent.sent_at
        self.assertEqual(sent.status, PurchaseOrder.Status.SENT)
        self.assertTrue(timezone.is_aware(sent.sent_at))
        self.assertGreaterEqual(sent.sent_at, approved.approved_at)
        with self.assertRaises(ValidationError):
            mark_purchase_order_sent(stale_order)
        sent.refresh_from_db()
        self.assertEqual(sent.sent_at, sent_at)

    def test_send_requires_approval_timestamp(self):
        order = self.create_order()
        PurchaseOrder.objects.filter(pk=order.pk).update(status=PurchaseOrder.Status.APPROVED)
        with self.assertRaises(ValidationError):
            mark_purchase_order_sent(order)

    def test_create_alternative_request(self):
        alternative = create_alternative_request(**self.alternative_data())
        self.assertEqual(alternative.request_item, self.request_item)
        self.assertEqual(alternative.status, AlternativeRequest.Status.REQUESTED)
        self.assertIsNone(alternative.technical_review_id)
        self.assertIsNone(alternative.client_decision)

    def test_identical_and_inconsistent_alternatives_are_rejected(self):
        for data in (
            self.alternative_data(alternative_nomenclature_id=self.request_item.nomenclature_id),
            self.alternative_data(project_id=uuid4()),
            self.alternative_data(original_nomenclature_id=uuid4()),
        ):
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    create_alternative_request(**data)
        self.assertFalse(AlternativeRequest.objects.exists())

    def test_record_delivery_preserves_tracking(self):
        order = self.create_order()
        delivery = record_expected_delivery(
            purchase_order=order,
            planned_date=date(2026, 10, 10),
            tracking={"carrier": "Carrier", "tracking_number": "AK-123"},
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.tracking["tracking_number"], "AK-123")
        self.assertEqual(delivery.status, ExpectedDelivery.Status.EXPECTED)
        self.assertIsNone(delivery.actual_date)

    def test_early_delivery_requires_reason_and_normalizes_whitespace(self):
        order = self.create_order()
        for reason in ("", " \t\n"):
            with self.subTest(reason=reason):
                with self.assertRaises(ValidationError):
                    record_expected_delivery(
                        purchase_order=order,
                        planned_date=date(2026, 10, 10),
                        actual_date=date(2026, 10, 9),
                        early_delivery_reason=reason,
                    )
        self.assertFalse(ExpectedDelivery.objects.exists())
        delivery = record_expected_delivery(
            purchase_order=order,
            planned_date=date(2026, 10, 10),
            actual_date=date(2026, 10, 9),
            early_delivery_reason="  Approved earlier delivery window  ",
            status=ExpectedDelivery.Status.DELIVERED,
        )
        self.assertEqual(delivery.early_delivery_reason, "Approved earlier delivery window")

    def test_delivery_rejects_unknown_status(self):
        with self.assertRaises(ValidationError):
            record_expected_delivery(
                purchase_order=self.create_order(),
                planned_date=date(2026, 10, 10),
                status="invalid",
            )
        self.assertFalse(ExpectedDelivery.objects.exists())
