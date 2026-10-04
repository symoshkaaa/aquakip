import uuid
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from procurement.models import RFQ, RFQRecipient, SupplierOffer, SupplierOfferItem
from procurement.tests.factories import (
    create_purchase_request,
    create_request_item,
    create_supplier,
)


class RFQModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.purchase_request = create_purchase_request()
        cls.request_item = create_request_item(cls.purchase_request)
        cls.rfq = RFQ.objects.create(purchase_request=cls.purchase_request)
        cls.offer = SupplierOffer.objects.create(
            rfq=cls.rfq,
            supplier=cls.supplier,
            offer_date=date(2026, 10, 3),
        )

    def create_offer_item(self, **overrides):
        data = {
            "supplier_offer": self.offer,
            "request_item": self.request_item,
            "nomenclature_id": self.request_item.nomenclature_id,
            "quantity": Decimal("2.000000"),
            "unit_price": Decimal("123.4567"),
        }
        return SupplierOfferItem.objects.create(**(data | overrides))

    def test_recipient_pair_is_unique_in_database(self):
        RFQRecipient.objects.create(rfq=self.rfq, supplier=self.supplier)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RFQRecipient.objects.create(rfq=self.rfq, supplier=self.supplier)

    def test_supplier_can_receive_multiple_rfqs(self):
        other_rfq = RFQ.objects.create(purchase_request=self.purchase_request)
        RFQRecipient.objects.create(rfq=self.rfq, supplier=self.supplier)
        RFQRecipient.objects.create(rfq=other_rfq, supplier=self.supplier)
        self.assertEqual(self.supplier.rfq_recipients.count(), 2)

    def test_offer_document_cannot_be_registered_twice_for_same_supplier_and_rfq(self):
        document_id = uuid.uuid4()
        self.offer.source_document_id = document_id
        self.offer.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SupplierOffer.objects.create(
                rfq=self.rfq,
                supplier=self.supplier,
                offer_date=date(2026, 10, 4),
                source_document_id=document_id,
            )

    def test_distinct_documents_and_missing_documents_allow_new_offers(self):
        for document_id in (uuid.uuid4(), uuid.uuid4(), None):
            SupplierOffer.objects.create(
                rfq=self.rfq,
                supplier=self.supplier,
                offer_date=self.offer.offer_date,
                source_document_id=document_id,
            )
        self.assertEqual(self.rfq.supplier_offers.count(), 4)

    def test_offer_valid_until_cannot_precede_offer_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SupplierOffer.objects.create(
                rfq=self.rfq,
                supplier=self.supplier,
                offer_date=date(2026, 10, 3),
                valid_until=date(2026, 10, 2),
            )

    def test_negative_quantity_and_price_are_rejected_by_database(self):
        for field, value in (
            ("quantity", Decimal("-0.000001")),
            ("unit_price", Decimal("-0.0001")),
        ):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.create_offer_item(**{field: value})

    def test_zero_quantity_and_price_are_allowed(self):
        item = self.create_offer_item(quantity=Decimal("0"), unit_price=Decimal("0"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("0.000000"))
        self.assertEqual(item.unit_price, Decimal("0.0000"))

    def test_negative_delivery_days_are_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_offer_item(delivery_days=-1)

    def test_duplicate_offer_line_is_rejected_but_alternative_is_allowed(self):
        self.create_offer_item()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_offer_item()
        self.create_offer_item(nomenclature_id=uuid.uuid4())
        self.assertEqual(self.offer.items.count(), 2)

    def test_all_new_primary_keys_are_generated_uuids(self):
        for model in (RFQ, RFQRecipient, SupplierOffer, SupplierOfferItem):
            with self.subTest(model=model.__name__):
                field = model._meta.pk
                self.assertIsInstance(field, models.UUIDField)
                self.assertIs(field.default, uuid.uuid4)
                self.assertFalse(field.editable)
                self.assertIsInstance(model().pk, uuid.UUID)

    def test_all_new_foreign_keys_stay_inside_procurement_and_protect_records(self):
        for model in (RFQ, RFQRecipient, SupplierOffer, SupplierOfferItem):
            for field in model._meta.fields:
                if isinstance(field, models.ForeignKey):
                    with self.subTest(model=model.__name__, field=field.name):
                        self.assertEqual(field.remote_field.model._meta.app_label, "procurement")
                        self.assertIs(field.remote_field.on_delete, models.PROTECT)
                        self.assertTrue(field.remote_field.related_name)
                        self.assertTrue(field.db_index)

    def test_external_identifiers_are_plain_uuid_fields(self):
        for model, name in (
            (SupplierOffer, "source_document_id"),
            (SupplierOfferItem, "nomenclature_id"),
        ):
            field = model._meta.get_field(name)
            self.assertIsInstance(field, models.UUIDField)
            self.assertIsNone(field.remote_field)
        self.assertTrue(SupplierOffer._meta.get_field("source_document_id").null)

    def test_choices_and_status_indexes_are_configured(self):
        for model, name, choices in (
            (RFQ, "status", RFQ.Status),
            (RFQRecipient, "channel", RFQRecipient.Channel),
            (RFQRecipient, "delivery_status", RFQRecipient.DeliveryStatus),
            (SupplierOffer, "status", SupplierOffer.Status),
            (SupplierOfferItem, "availability", SupplierOfferItem.Availability),
            (SupplierOfferItem, "technical_match", SupplierOfferItem.TechnicalMatch),
        ):
            field = model._meta.get_field(name)
            self.assertIsInstance(field, models.CharField)
            self.assertTrue(issubclass(choices, models.TextChoices))
            self.assertEqual(field.choices, choices.choices)
            if name in ("status", "delivery_status"):
                self.assertTrue(field.db_index)

    def test_decimal_precision_and_aware_timestamps(self):
        item = self.create_offer_item()
        for name, precision in (("quantity", 6), ("unit_price", 4)):
            field = SupplierOfferItem._meta.get_field(name)
            self.assertIsInstance(field, models.DecimalField)
            self.assertEqual((field.max_digits, field.decimal_places), (20, precision))
        recipient = RFQRecipient.objects.create(rfq=self.rfq, supplier=self.supplier)
        for instance in (self.rfq, recipient, self.offer, item):
            self.assertTrue(timezone.is_aware(instance.created_at))
            self.assertTrue(timezone.is_aware(instance.updated_at))

    def test_linked_business_entities_cannot_be_deleted(self):
        self.create_offer_item()
        for instance in (
            self.purchase_request,
            self.request_item,
            self.supplier,
            self.rfq,
            self.offer,
        ):
            with self.subTest(model=type(instance).__name__):
                with self.assertRaises(ProtectedError):
                    instance.delete()
