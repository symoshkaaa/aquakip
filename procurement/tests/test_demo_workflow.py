from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from procurement.management.commands.seed_procurement_demo import demo_id
from procurement.models import (
    AlternativeRequest, ExpectedDelivery, PurchaseOrder, PurchaseOrderItem,
    PurchaseRequest, PurchaseRequestItem, RFQ, RFQRecipient, Supplier,
    SupplierComparison, SupplierOffer, SupplierOfferItem,
)
from procurement.services import approve_purchase_order, create_purchase_request


class DemoEntryPointAPITests(APITestCase):
    def request_payload(self, **overrides):
        return {
            "project_id": str(uuid4()), "specification_version_id": str(uuid4()),
            "requested_by": str(uuid4()), "items": [{
                "nomenclature_id": str(uuid4()), "unit_id": str(uuid4()),
                "quantity": "2.123456", "budget_price": "100.1234", "route_type": "standard",
            }],
        } | overrides

    def test_supplier_create_search_status_and_detail(self):
        response = self.client.post(reverse("procurement:supplier-list"), {
            "code": "SUP-DEMO", "name": "Aqua Supplier", "status": Supplier.Status.ACTIVE,
            "rating": "4.750", "email": "sales@example.com",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        supplier_id = response.json()["id"]
        detail = self.client.get(reverse("procurement:supplier-detail", args=[supplier_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["rating"], "4.750")
        for params, count in (({"search": "aqua"}, 1), ({"search": "missing"}, 0),
                              ({"status": Supplier.Status.BLOCKED}, 0)):
            listing = self.client.get(reverse("procurement:supplier-list"), params)
            self.assertEqual(listing.json()["count"], count)

    def test_supplier_validation_rejects_duplicate_code_and_invalid_status(self):
        self.client.post(reverse("procurement:supplier-list"), {
            "code": "SUP-001", "name": "Supplier",
        }, format="json")
        for data in ({"code": "SUP-001", "name": "Duplicate"},
                     {"code": "SUP-002", "name": "Invalid", "status": "unknown"}):
            response = self.client.post(reverse("procurement:supplier-list"), data, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Supplier.objects.count(), 1)

    def test_nested_purchase_request_creation_and_detail(self):
        payload = self.request_payload()
        payload["items"].append({
            "nomenclature_id": str(uuid4()), "unit_id": str(uuid4()),
            "quantity": "1.000000", "budget_price": None,
        })
        response = self.client.post(reverse("procurement:purchase-request-list"), payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        data = response.json()
        self.assertEqual(data["status"], PurchaseRequest.Status.DRAFT)
        self.assertEqual([item["position"] for item in data["items"]], [1, 2])
        self.assertEqual(data["items"][0]["quantity"], "2.123456")
        self.assertEqual(data["items"][0]["estimated_unit_price"], "100.1234")
        self.assertEqual(data["items"][1]["estimated_unit_price"], "0.0000")
        detail = self.client.get(reverse("procurement:purchase-request-detail", args=[data["id"]]))
        self.assertEqual(len(detail.json()["items"]), 2)
        listing = self.client.get(reverse("procurement:purchase-request-list"))
        self.assertEqual(listing.json()["count"], 1)

    def test_nested_request_rejects_empty_negative_and_duplicate_positions(self):
        for items in ([], [{"nomenclature_id": str(uuid4()), "unit_id": str(uuid4()), "quantity": "-1"}],
                      [{"nomenclature_id": str(uuid4()), "unit_id": str(uuid4()), "quantity": "1", "position": 1}] * 2):
            with self.subTest(items=items):
                response = self.client.post(
                    reverse("procurement:purchase-request-list"), self.request_payload(items=items), format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(PurchaseRequest.objects.exists())
                self.assertFalse(PurchaseRequestItem.objects.exists())

    def test_request_service_rolls_back_a_later_invalid_item(self):
        payload = self.request_payload()
        with self.assertRaises(ValidationError):
            create_purchase_request(
                project_id=payload["project_id"], specification_version_id=payload["specification_version_id"],
                requested_by=payload["requested_by"],
                items=[payload["items"][0], payload["items"][0] | {"quantity": "-1"}],
            )
        self.assertFalse(PurchaseRequest.objects.exists())
        self.assertFalse(PurchaseRequestItem.objects.exists())

    def test_real_rfq_offer_and_comparison_filters(self):
        call_command("seed_procurement_demo", stdout=StringIO())
        empty_rfq = str(demo_id("rfq-2"))
        empty_request = str(demo_id("request-2"))
        offers = self.client.get(reverse("procurement:supplier-offer-list"), {"rfq": empty_rfq})
        self.assertEqual(offers.json()["count"], 0)
        offers = self.client.get(reverse("procurement:supplier-offer-list"), {"rfq": str(demo_id("rfq-1"))})
        self.assertEqual(offers.json()["count"], 3)
        self.assertTrue(all(offer["rfq"] == str(demo_id("rfq-1")) for offer in offers.json()["results"]))
        comparisons = self.client.get(reverse("procurement:supplier-comparison-list"), {"purchase_request": empty_request})
        self.assertEqual(comparisons.json()["count"], 0)
        rfqs = self.client.get(reverse("procurement:rfq-list"), {"purchase_request": empty_request})
        self.assertEqual(rfqs.json()["count"], 1)


class ProcurementSeedTests(TestCase):
    def test_seed_is_linked_valid_and_idempotent(self):
        counts = {
            Supplier: 3, PurchaseRequest: 2, PurchaseRequestItem: 4,
            RFQ: 2, RFQRecipient: 6, SupplierOffer: 3, SupplierOfferItem: 6,
            SupplierComparison: 1, PurchaseOrder: 3, PurchaseOrderItem: 6,
            ExpectedDelivery: 2, AlternativeRequest: 1,
        }
        for _ in range(2):
            call_command("seed_procurement_demo", stdout=StringIO())
            for model, count in counts.items():
                self.assertEqual(model.objects.count(), count, model.__name__)
                for record in model.objects.all():
                    record.full_clean()
        self.assertEqual(set(PurchaseOrder.objects.values_list("status", flat=True)), {
            PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.SENT,
        })
        comparison = SupplierComparison.objects.get()
        self.assertTrue(SupplierOffer.objects.filter(pk=comparison.result["selected_offer_id"]).exists())

    def test_seed_does_not_reset_an_approved_demo_order(self):
        call_command("seed_procurement_demo", stdout=StringIO())
        order = PurchaseOrder.objects.get(number="DEMO-PO-001")
        order = approve_purchase_order(order)
        approved_at = order.approved_at
        call_command("seed_procurement_demo", stdout=StringIO())
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.APPROVED)
        self.assertEqual(order.approved_at, approved_at)
