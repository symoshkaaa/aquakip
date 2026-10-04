from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from procurement.models import RFQ, RFQRecipient, SupplierOffer, SupplierOfferItem
from procurement.services import add_rfq_recipient, create_rfq, register_supplier_offer
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class ProcurementServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)
        cls.rfq = RFQ.objects.create(purchase_request=cls.purchase_request)

    def offer_data(self, **overrides):
        return {"offer_date": date(2026, 10, 3), "currency_code": "KZT"} | overrides

    def item_data(self, **overrides):
        return {
            "request_item": self.request_item,
            "nomenclature_id": self.request_item.nomenclature_id,
            "quantity": Decimal("2.123456"),
            "unit_price": Decimal("10.1234"),
        } | overrides

    def test_create_rfq(self):
        deadline = timezone.now() + timedelta(days=7)
        rfq = create_rfq(self.purchase_request, status=RFQ.Status.OPEN, deadline_at=deadline)
        rfq.refresh_from_db()
        self.assertEqual(rfq.purchase_request, self.purchase_request)
        self.assertEqual(rfq.status, RFQ.Status.OPEN)
        self.assertEqual(rfq.deadline_at, deadline)
        self.assertTrue(timezone.is_aware(rfq.created_at))

    def test_create_rfq_rejects_unknown_status(self):
        with self.assertRaises(ValidationError):
            create_rfq(self.purchase_request, status="invalid")
        self.assertEqual(RFQ.objects.count(), 1)

    def test_add_rfq_recipient(self):
        sent_at = timezone.now()
        recipient = add_rfq_recipient(
            self.rfq,
            self.supplier,
            channel=RFQRecipient.Channel.PORTAL,
            sent_at=sent_at,
            delivery_status=RFQRecipient.DeliveryStatus.SENT,
        )
        recipient.refresh_from_db()
        self.assertEqual(recipient.rfq, self.rfq)
        self.assertEqual(recipient.supplier, self.supplier)
        self.assertEqual(recipient.channel, RFQRecipient.Channel.PORTAL)
        self.assertEqual(recipient.sent_at, sent_at)

    def test_add_rfq_recipient_rejects_duplicate(self):
        add_rfq_recipient(self.rfq, self.supplier)
        with self.assertRaises(ValidationError):
            add_rfq_recipient(self.rfq, self.supplier)
        self.assertEqual(self.rfq.recipients.count(), 1)

    def test_add_rfq_recipient_rejects_unknown_choices(self):
        for data in ({"channel": "invalid"}, {"delivery_status": "invalid"}):
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    add_rfq_recipient(self.rfq, self.supplier, **data)
        self.assertFalse(self.rfq.recipients.exists())

    def test_register_offer_with_multiple_items(self):
        second_item = create_request_item(self.purchase_request, position=2)
        document_id = uuid4()
        offer = register_supplier_offer(
            self.rfq,
            self.supplier,
            self.offer_data(source_document_id=document_id),
            [
                self.item_data(),
                self.item_data(request_item=second_item, nomenclature_id=second_item.nomenclature_id),
            ],
        )
        self.assertEqual(offer.rfq, self.rfq)
        self.assertEqual(offer.supplier, self.supplier)
        self.assertEqual(offer.source_document_id, document_id)
        self.assertEqual(offer.status, SupplierOffer.Status.RECEIVED)
        self.assertEqual(offer.items.count(), 2)
        first_item = offer.items.get(request_item=self.request_item)
        self.assertEqual(first_item.quantity, Decimal("2.123456"))
        self.assertEqual(first_item.unit_price, Decimal("10.1234"))

    def test_invalid_later_item_rolls_back_offer_and_preceding_items(self):
        second_item = create_request_item(self.purchase_request, position=2)
        for field, value in (
            ("quantity", Decimal("-0.000001")),
            ("unit_price", Decimal("-0.0001")),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    register_supplier_offer(
                        self.rfq,
                        self.supplier,
                        self.offer_data(),
                        [self.item_data(), self.item_data(request_item=second_item, **{field: value})],
                    )
                self.assertFalse(SupplierOffer.objects.exists())
                self.assertFalse(SupplierOfferItem.objects.exists())

    def test_item_from_another_purchase_request_rolls_back_offer(self):
        foreign_item = create_request_item(create_purchase_request())
        with self.assertRaisesMessage(ValidationError, "RFQ purchase request"):
            register_supplier_offer(
                self.rfq,
                self.supplier,
                self.offer_data(),
                [self.item_data(), self.item_data(request_item=foreign_item)],
            )
        self.assertFalse(SupplierOffer.objects.exists())
        self.assertFalse(SupplierOfferItem.objects.exists())

    def test_empty_offer_is_rejected(self):
        with self.assertRaises(ValidationError):
            register_supplier_offer(self.rfq, self.supplier, self.offer_data(), [])
        self.assertFalse(SupplierOffer.objects.exists())

    def test_duplicate_document_is_rejected_without_new_items(self):
        data = self.offer_data(source_document_id=uuid4())
        register_supplier_offer(self.rfq, self.supplier, data, [self.item_data()])
        with self.assertRaises(ValidationError):
            register_supplier_offer(self.rfq, self.supplier, data, [self.item_data()])
        self.assertEqual(SupplierOffer.objects.count(), 1)
        self.assertEqual(SupplierOfferItem.objects.count(), 1)

    def test_duplicate_line_rolls_back_entire_offer(self):
        with self.assertRaises(ValidationError):
            register_supplier_offer(
                self.rfq, self.supplier, self.offer_data(), [self.item_data(), self.item_data()]
            )
        self.assertFalse(SupplierOffer.objects.exists())
        self.assertFalse(SupplierOfferItem.objects.exists())

    def test_invalid_offer_dates_and_currency_are_rejected(self):
        for data in (
            self.offer_data(valid_until=date(2026, 10, 2)),
            self.offer_data(currency_code="KZ"),
            self.offer_data(currency_code="kzt"),
        ):
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    register_supplier_offer(self.rfq, self.supplier, data, [self.item_data()])
        self.assertFalse(SupplierOffer.objects.exists())
