from uuid import uuid4

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from procurement.models import RFQ, RFQRecipient, SupplierOffer, SupplierOfferItem
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class ProcurementAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)
        cls.rfq = RFQ.objects.create(purchase_request=cls.purchase_request)

    def recipients_url(self, rfq=None):
        return reverse("procurement:rfq-recipients", args=[(rfq or self.rfq).pk])

    def item_payload(self, **overrides):
        return {
            "request_item": str(self.request_item.pk),
            "nomenclature_id": str(self.request_item.nomenclature_id),
            "quantity": "2.123456",
            "unit_price": "10.1234",
            "availability": "in_stock",
            "delivery_days": 5,
            "technical_match": "not_reviewed",
        } | overrides

    def offer_payload(self, **overrides):
        return {
            "rfq": str(self.rfq.pk),
            "supplier": str(self.supplier.pk),
            "currency_code": "KZT",
            "offer_date": "2026-10-03",
            "valid_until": "2026-10-31",
            "source_document_id": str(uuid4()),
            "items": [self.item_payload()],
        } | overrides

    def test_create_list_and_retrieve_rfq(self):
        response = self.client.post(
            reverse("procurement:rfq-list"),
            {
                "purchase_request": str(self.purchase_request.pk),
                "status": "open",
                "deadline_at": "2026-10-10T15:00:00+05:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["deadline_at"], "2026-10-10T10:00:00Z")
        rfq = RFQ.objects.get(pk=response.data["id"])
        self.assertTrue(timezone.is_aware(rfq.deadline_at))
        detail = self.client.get(reverse("procurement:rfq-detail", args=[rfq.pk]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], str(rfq.pk))
        listing = self.client.get(reverse("procurement:rfq-list"), {"limit": 1})
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 2)
        self.assertEqual(len(listing.data["results"]), 1)
        self.assertIsNotNone(listing.data["next"])

    def test_rfq_invalid_status_and_missing_purchase_request_return_400(self):
        for payload in (
            {"purchase_request": str(self.purchase_request.pk), "status": "invalid"},
            {"purchase_request": str(uuid4())},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(reverse("procurement:rfq-list"), payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(RFQ.objects.count(), 1)

    def test_add_and_list_recipients_scoped_to_url_rfq(self):
        other_rfq = RFQ.objects.create(purchase_request=self.purchase_request)
        RFQRecipient.objects.create(rfq=other_rfq, supplier=create_supplier())
        response = self.client.post(
            self.recipients_url(),
            {"supplier": str(self.supplier.pk), "channel": "email", "rfq": str(other_rfq.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.json()["rfq"], str(self.rfq.pk))
        listing = self.client.get(self.recipients_url())
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["id"], response.data["id"])

    def test_duplicate_recipient_returns_400(self):
        payload = {"supplier": str(self.supplier.pk)}
        first = self.client.post(self.recipients_url(), payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(self.recipients_url(), payload, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST, duplicate.data)
        self.assertEqual(self.rfq.recipients.count(), 1)

    def test_invalid_recipient_channel_returns_400(self):
        response = self.client.post(
            self.recipients_url(),
            {"supplier": str(self.supplier.pk), "channel": "invalid"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.rfq.recipients.exists())

    def test_create_list_and_retrieve_offer_with_items(self):
        payload = self.offer_payload()
        response = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["source_document_id"], payload["source_document_id"])
        self.assertEqual(response.data["items"][0]["quantity"], "2.123456")
        self.assertEqual(response.data["items"][0]["unit_price"], "10.1234")
        self.assertEqual(response.json()["items"][0]["request_item"], str(self.request_item.pk))
        offer = SupplierOffer.objects.get(pk=response.data["id"])
        self.assertEqual(offer.items.count(), 1)
        detail = self.client.get(reverse("procurement:supplier-offer-detail", args=[offer.pk]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.data["items"]), 1)
        listing = self.client.get(reverse("procurement:supplier-offer-list"))
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)

    def test_negative_quantity_and_price_are_validated_before_persistence(self):
        for field, value in (("quantity", "-0.000001"), ("unit_price", "-0.0001")):
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("procurement:supplier-offer-list"),
                    self.offer_payload(items=[self.item_payload(**{field: value})]),
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn(field, response.data["items"][0])
                self.assertFalse(SupplierOffer.objects.exists())
                self.assertFalse(SupplierOfferItem.objects.exists())

    def test_duplicate_offer_document_returns_400(self):
        payload = self.offer_payload()
        first = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST, duplicate.data)
        self.assertEqual(SupplierOffer.objects.count(), 1)
        self.assertEqual(SupplierOfferItem.objects.count(), 1)

    def test_offer_item_from_another_request_returns_400_and_rolls_back(self):
        foreign_item = create_request_item(create_purchase_request())
        payload = self.offer_payload(
            items=[self.item_payload(), self.item_payload(request_item=str(foreign_item.pk))]
        )
        response = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("items", response.data)
        self.assertFalse(SupplierOffer.objects.exists())
        self.assertFalse(SupplierOfferItem.objects.exists())

    def test_duplicate_offer_lines_return_400_and_roll_back(self):
        payload = self.offer_payload(items=[self.item_payload(), self.item_payload()])
        response = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(SupplierOffer.objects.exists())
        self.assertFalse(SupplierOfferItem.objects.exists())

    def test_empty_offer_and_invalid_dates_return_400(self):
        for payload in (self.offer_payload(items=[]), self.offer_payload(valid_until="2026-10-02")):
            with self.subTest(payload=payload):
                response = self.client.post(reverse("procurement:supplier-offer-list"), payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(SupplierOffer.objects.exists())

    def test_missing_resources_return_404(self):
        for name in ("rfq-detail", "rfq-recipients", "supplier-offer-detail"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"procurement:{name}", args=[uuid4()]))
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_browser_accept_headers_negotiate_json(self):
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        for name in ("rfq-list", "supplier-offer-list", "api-root"):
            with self.subTest(name=name):
                response = self.client.get(
                    reverse(f"procurement:{name}"), HTTP_ACCEPT=accept
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response["Content-Type"], "application/json")

        html_only = self.client.get(
            reverse("procurement:rfq-list"), HTTP_ACCEPT="text/html"
        )
        self.assertEqual(html_only.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_unimplemented_mutations_are_not_exposed(self):
        url = reverse("procurement:rfq-detail", args=[self.rfq.pk])
        for method in (self.client.patch, self.client.delete):
            response = method(url, {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(RFQ.objects.filter(pk=self.rfq.pk).exists())
