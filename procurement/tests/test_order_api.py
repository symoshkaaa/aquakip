from uuid import uuid4

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierComparison,
)
from procurement.services import create_purchase_order
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class ProcurementOrderAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)
        cls.order = create_purchase_order(
            project_id=cls.purchase_request.project_id,
            supplier=cls.supplier,
            number="PO-001",
            currency_code="KZT",
            items=[{
                "nomenclature_id": cls.request_item.nomenclature_id,
                "quantity": "2.000000",
                "unit_price": "10.0000",
            }],
        )

    def item_payload(self, **overrides):
        return {
            "nomenclature_id": str(self.request_item.nomenclature_id),
            "quantity": "2.123456",
            "unit_price": "10.1234",
            "expected_date": "2026-10-10",
        } | overrides

    def order_payload(self, **overrides):
        return {
            "project_id": str(self.purchase_request.project_id),
            "supplier": str(self.supplier.pk),
            "number": "PO-002",
            "currency_code": "KZT",
            "items": [self.item_payload()],
        } | overrides

    def alternative_payload(self, **overrides):
        return {
            "project_id": str(self.purchase_request.project_id),
            "request_item": str(self.request_item.pk),
            "original_nomenclature_id": str(self.request_item.nomenclature_id),
            "alternative_nomenclature_id": str(uuid4()),
        } | overrides

    def delivery_payload(self, **overrides):
        return {
            "purchase_order": str(self.order.pk),
            "planned_date": "2026-10-10",
            "tracking": {"carrier": "Carrier", "tracking_number": "AK-123"},
        } | overrides

    def post_resource(self, name, payload):
        return self.client.post(reverse(f"procurement:{name}-list"), payload, format="json")

    def assert_list_and_detail(self, name, resource_id, expected_count=1):
        detail = self.client.get(reverse(f"procurement:{name}-detail", args=[resource_id]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(detail.json()["id"], resource_id)
        listing = self.client.get(reverse(f"procurement:{name}-list"))
        self.assertEqual(listing.status_code, status.HTTP_200_OK, listing.data)
        self.assertEqual(listing.json()["count"], expected_count)
        return detail.json()

    def test_create_list_and_retrieve_comparison(self):
        response = self.post_resource("supplier-comparison", {
            "purchase_request": str(self.purchase_request.pk),
            "version": 1,
            "criteria": {"price_weight": 70},
            "result": {"selected_supplier_id": str(self.supplier.pk)},
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        detail = self.assert_list_and_detail("supplier-comparison", response.json()["id"])
        self.assertEqual(detail["criteria"], {"price_weight": 70})
        self.assertEqual(detail["result"]["selected_supplier_id"], str(self.supplier.pk))

    def test_comparison_json_defaults_do_not_cause_server_error(self):
        response = self.post_resource("supplier-comparison", {
            "purchase_request": str(self.purchase_request.pk), "version": 1,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.json()["criteria"], {})
        self.assertEqual(response.json()["result"], {})

    def test_duplicate_and_nonpositive_comparison_versions_return_400(self):
        first = self.post_resource("supplier-comparison", {
            "purchase_request": str(self.purchase_request.pk), "version": 1,
        })
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        for version in (1, 0, -1):
            with self.subTest(version=version):
                response = self.post_resource("supplier-comparison", {
                    "purchase_request": str(self.purchase_request.pk), "version": version,
                })
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(SupplierComparison.objects.count(), 1)

    def test_create_order_ignores_client_total_and_workflow_fields(self):
        response = self.post_resource("purchase-order", self.order_payload(
            total_amount="9999999999999999.9999",
            status="sent",
            approved_at="2026-10-04T10:00:00Z",
            sent_at="2026-10-04T10:01:00Z",
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        data = response.json()
        self.assertEqual(data["total_amount"], "21.4966")
        self.assertEqual(data["status"], "draft")
        self.assertIsNone(data["approved_at"])
        self.assertIsNone(data["sent_at"])
        self.assertEqual(data["items"][0]["quantity"], "2.123456")
        self.assertEqual(data["items"][0]["unit_price"], "10.1234")
        self.assertEqual(data["project_id"], str(self.purchase_request.project_id))
        detail = self.assert_list_and_detail("purchase-order", data["id"], expected_count=2)
        self.assertEqual(detail["items"], data["items"])

    def test_empty_and_missing_order_items_return_400(self):
        missing_items = self.order_payload()
        missing_items.pop("items")
        for payload in (self.order_payload(items=[]), missing_items):
            with self.subTest(payload=payload):
                response = self.post_resource("purchase-order", payload)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_negative_order_quantity_and_price_return_400(self):
        for field, value in (("quantity", "-0.000001"), ("unit_price", "-0.0001")):
            with self.subTest(field=field):
                response = self.post_resource("purchase-order", self.order_payload(
                    items=[self.item_payload(**{field: value})]
                ))
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn(field, response.data["items"][0])
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(PurchaseOrderItem.objects.count(), 1)

    def test_order_total_overflow_returns_400_and_rolls_back(self):
        response = self.post_resource("purchase-order", self.order_payload(items=[
            self.item_payload(
                quantity="99999999999999.999999",
                unit_price="9999999999999999.9999",
            )
        ]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(PurchaseOrderItem.objects.count(), 1)

    def test_duplicate_order_number_and_invalid_currency_return_400(self):
        for payload in (
            self.order_payload(number=self.order.number),
            self.order_payload(currency_code="KZ"),
            self.order_payload(currency_code="kzt"),
        ):
            with self.subTest(payload=payload):
                response = self.post_resource("purchase-order", payload)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_send_before_approve_returns_400(self):
        response = self.client.post(
            reverse("procurement:purchase-order-send", args=[self.order.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.DRAFT)
        self.assertIsNone(self.order.sent_at)

    def test_approve_send_and_repeated_actions(self):
        approve_url = reverse("procurement:purchase-order-approve", args=[self.order.pk])
        send_url = reverse("procurement:purchase-order-send", args=[self.order.pk])
        approved = self.client.post(approve_url, {}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertEqual(approved.json()["status"], "approved")
        approved_at = approved.json()["approved_at"]
        repeated = self.client.post(approve_url, {}, format="json")
        self.assertEqual(repeated.status_code, status.HTTP_400_BAD_REQUEST, repeated.data)
        sent = self.client.post(send_url, {}, format="json")
        self.assertEqual(sent.status_code, status.HTTP_200_OK, sent.data)
        self.assertEqual(sent.json()["status"], "sent")
        self.assertEqual(sent.json()["approved_at"], approved_at)
        sent_at = sent.json()["sent_at"]
        repeated_send = self.client.post(send_url, {}, format="json")
        self.assertEqual(repeated_send.status_code, status.HTTP_400_BAD_REQUEST, repeated_send.data)
        self.order.refresh_from_db()
        self.assertTrue(timezone.is_aware(self.order.approved_at))
        self.assertTrue(timezone.is_aware(self.order.sent_at))
        detail = self.client.get(reverse("procurement:purchase-order-detail", args=[self.order.pk]))
        self.assertEqual(detail.json()["sent_at"], sent_at)

    def test_cancelled_order_cannot_be_approved_or_sent(self):
        PurchaseOrder.objects.filter(pk=self.order.pk).update(status=PurchaseOrder.Status.CANCELLED)
        for action in ("approve", "send"):
            with self.subTest(action=action):
                response = self.client.post(
                    reverse(f"procurement:purchase-order-{action}", args=[self.order.pk]),
                    {}, format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_create_list_and_retrieve_alternative(self):
        response = self.post_resource("alternative-request", self.alternative_payload(
            status="approved", technical_review_id=str(uuid4()), client_decision="approved",
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        detail = self.assert_list_and_detail("alternative-request", response.json()["id"])
        self.assertEqual(detail["status"], "requested")
        self.assertIsNone(detail["technical_review_id"])
        self.assertIsNone(detail["client_decision"])
        self.assertEqual(detail["request_item"], str(self.request_item.pk))

    def test_identical_and_inconsistent_alternatives_return_400(self):
        for payload in (
            self.alternative_payload(alternative_nomenclature_id=str(self.request_item.nomenclature_id)),
            self.alternative_payload(project_id=str(uuid4())),
            self.alternative_payload(original_nomenclature_id=str(uuid4())),
        ):
            with self.subTest(payload=payload):
                response = self.post_resource("alternative-request", payload)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(AlternativeRequest.objects.exists())

    def test_create_list_and_retrieve_delivery(self):
        response = self.post_resource("expected-delivery", self.delivery_payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        detail = self.assert_list_and_detail("expected-delivery", response.json()["id"])
        self.assertEqual(detail["tracking"]["tracking_number"], "AK-123")
        self.assertIsNone(detail["actual_date"])

    def test_early_delivery_without_reason_returns_400(self):
        for reason in ("", " \t\n"):
            with self.subTest(reason=reason):
                response = self.post_resource("expected-delivery", self.delivery_payload(
                    actual_date="2026-10-09", early_delivery_reason=reason,
                ))
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(ExpectedDelivery.objects.exists())

    def test_early_delivery_with_reason_is_allowed(self):
        response = self.post_resource("expected-delivery", self.delivery_payload(
            actual_date="2026-10-09",
            early_delivery_reason="Approved earlier delivery window",
            status="delivered",
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.json()["early_delivery_reason"], "Approved earlier delivery window")
        self.assertEqual(response.json()["actual_date"], "2026-10-09")

    def test_on_time_and_late_deliveries_need_no_reason(self):
        for actual_date in ("2026-10-10", "2026-10-11"):
            with self.subTest(actual_date=actual_date):
                response = self.post_resource("expected-delivery", self.delivery_payload(
                    actual_date=actual_date, status="delivered",
                ))
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_missing_resources_and_order_actions_return_404(self):
        for name in (
            "supplier-comparison", "purchase-order", "alternative-request", "expected-delivery",
        ):
            response = self.client.get(reverse(f"procurement:{name}-detail", args=[uuid4()]))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        for action in ("approve", "send"):
            response = self.client.post(
                reverse(f"procurement:purchase-order-{action}", args=[uuid4()]), {}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_actions_accept_post_only(self):
        for action in ("approve", "send"):
            response = self.client.get(
                reverse(f"procurement:purchase-order-{action}", args=[self.order.pk])
            )
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
