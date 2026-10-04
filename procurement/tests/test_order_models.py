import uuid
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierComparison,
)
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class ProcurementOrderModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)
        cls.order = PurchaseOrder.objects.create(
            project_id=cls.purchase_request.project_id,
            supplier=cls.supplier,
            number="PO-001",
            currency_code="KZT",
            total_amount=Decimal("20.0000"),
        )

    def create_item(self, **overrides):
        data = {
            "purchase_order": self.order,
            "nomenclature_id": self.request_item.nomenclature_id,
            "quantity": Decimal("2.000000"),
            "unit_price": Decimal("10.0000"),
        }
        return PurchaseOrderItem.objects.create(**(data | overrides))

    def test_comparison_version_is_unique_per_request(self):
        SupplierComparison.objects.create(purchase_request=self.purchase_request, version=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SupplierComparison.objects.create(purchase_request=self.purchase_request, version=1)
        SupplierComparison.objects.create(purchase_request=create_purchase_request(), version=1)
        self.assertEqual(SupplierComparison.objects.count(), 2)

    def test_comparison_version_must_be_positive(self):
        for version in (0, -1):
            with self.subTest(version=version):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    SupplierComparison.objects.create(
                        purchase_request=self.purchase_request, version=version
                    )

    def test_order_number_is_unique_per_project_across_suppliers(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseOrder.objects.create(
                project_id=self.order.project_id,
                supplier=create_supplier(),
                number=self.order.number,
                currency_code="KZT",
            )

    def test_order_number_can_be_reused_in_another_project(self):
        PurchaseOrder.objects.create(
            project_id=uuid.uuid4(),
            supplier=self.supplier,
            number=self.order.number,
            currency_code="KZT",
        )
        self.assertEqual(PurchaseOrder.objects.count(), 2)

    def test_order_total_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseOrder.objects.filter(pk=self.order.pk).update(total_amount=Decimal("-0.0001"))

    def test_negative_item_quantity_and_price_are_rejected_by_database(self):
        for field, value in (
            ("quantity", Decimal("-0.000001")),
            ("unit_price", Decimal("-0.0001")),
        ):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.create_item(**{field: value})

    def test_zero_item_quantity_and_price_are_allowed(self):
        item = self.create_item(quantity=Decimal("0"), unit_price=Decimal("0"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("0.000000"))
        self.assertEqual(item.unit_price, Decimal("0.0000"))

    def test_alternative_cannot_reference_the_original_nomenclature(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AlternativeRequest.objects.create(
                project_id=self.order.project_id,
                request_item=self.request_item,
                original_nomenclature_id=self.request_item.nomenclature_id,
                alternative_nomenclature_id=self.request_item.nomenclature_id,
            )

    def test_early_delivery_requires_nonblank_reason_in_database(self):
        for reason in ("", " \t\n"):
            with self.subTest(reason=reason):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ExpectedDelivery.objects.create(
                        purchase_order=self.order,
                        planned_date=date(2026, 10, 10),
                        actual_date=date(2026, 10, 9),
                        early_delivery_reason=reason,
                    )

    def test_delivery_dates_allow_unknown_on_time_late_and_justified_early(self):
        for actual_date, reason in (
            (None, ""),
            (date(2026, 10, 10), ""),
            (date(2026, 10, 11), ""),
            (date(2026, 10, 9), "Approved earlier delivery window"),
        ):
            ExpectedDelivery.objects.create(
                purchase_order=self.order,
                planned_date=date(2026, 10, 10),
                actual_date=actual_date,
                early_delivery_reason=reason,
            )
        self.assertEqual(self.order.expected_deliveries.count(), 4)

    def test_uuid_primary_keys_and_foreign_keys_preserve_service_boundary(self):
        for model in (
            SupplierComparison,
            PurchaseOrder,
            PurchaseOrderItem,
            AlternativeRequest,
            ExpectedDelivery,
        ):
            with self.subTest(model=model.__name__):
                self.assertIsInstance(model._meta.pk, models.UUIDField)
                self.assertIs(model._meta.pk.default, uuid.uuid4)
                self.assertFalse(model._meta.pk.editable)
                for field in model._meta.fields:
                    if isinstance(field, models.ForeignKey):
                        self.assertEqual(field.remote_field.model._meta.app_label, "procurement")
                        self.assertIs(field.remote_field.on_delete, models.PROTECT)
                        self.assertTrue(field.remote_field.related_name)
                        self.assertTrue(field.db_index)

    def test_external_identifiers_are_plain_uuid_fields(self):
        for model, names in (
            (PurchaseOrder, ("project_id",)),
            (PurchaseOrderItem, ("nomenclature_id",)),
            (AlternativeRequest, (
                "project_id", "original_nomenclature_id",
                "alternative_nomenclature_id", "technical_review_id",
            )),
        ):
            for name in names:
                with self.subTest(model=model.__name__, field=name):
                    field = model._meta.get_field(name)
                    self.assertIsInstance(field, models.UUIDField)
                    self.assertIsNone(field.remote_field)

    def test_status_choices_project_indexes_and_decimal_precision(self):
        for model in (PurchaseOrder, AlternativeRequest, ExpectedDelivery):
            field = model._meta.get_field("status")
            self.assertIsInstance(field, models.CharField)
            self.assertEqual(field.choices, model.Status.choices)
            self.assertTrue(issubclass(model.Status, models.TextChoices))
            self.assertTrue(field.db_index)
        for model in (PurchaseOrder, AlternativeRequest):
            self.assertTrue(model._meta.get_field("project_id").db_index)
        for model, name, places in (
            (PurchaseOrder, "total_amount", 4),
            (PurchaseOrderItem, "quantity", 6),
            (PurchaseOrderItem, "unit_price", 4),
        ):
            field = model._meta.get_field(name)
            self.assertIsInstance(field, models.DecimalField)
            self.assertEqual((field.max_digits, field.decimal_places), (20, places))

    def test_linked_records_are_protected_and_timestamps_are_aware(self):
        item = self.create_item()
        comparison = SupplierComparison.objects.create(
            purchase_request=self.purchase_request, version=1
        )
        alternative = AlternativeRequest.objects.create(
            project_id=self.order.project_id,
            request_item=self.request_item,
            original_nomenclature_id=self.request_item.nomenclature_id,
            alternative_nomenclature_id=uuid.uuid4(),
        )
        delivery = ExpectedDelivery.objects.create(
            purchase_order=self.order, planned_date=date(2026, 10, 10)
        )
        for instance in (self.order, item, comparison, alternative, delivery):
            self.assertTrue(timezone.is_aware(instance.created_at))
            self.assertTrue(timezone.is_aware(instance.updated_at))
        for instance in (self.order, self.supplier, self.purchase_request, self.request_item):
            with self.subTest(model=type(instance).__name__):
                with self.assertRaises(ProtectedError):
                    instance.delete()
