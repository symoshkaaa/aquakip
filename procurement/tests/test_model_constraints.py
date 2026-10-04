from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import ForeignKey, UUIDField
from django.test import TestCase
from django.utils import timezone

from procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierAgreement,
)


class ProcurementModelConstraintTests(TestCase):
    def create_supplier(self, code: str = "SUP-001") -> Supplier:
        return Supplier.objects.create(code=code, name=f"Supplier {code}")

    def create_agreement(
        self,
        supplier: Supplier | None = None,
        agreement_number: str = "AGR-001",
        contract_number: str | None = None,
    ) -> SupplierAgreement:
        return SupplierAgreement.objects.create(
            supplier=supplier or self.create_supplier(),
            agreement_number=agreement_number,
            contract_number=contract_number,
            status=SupplierAgreement.Status.ACTIVE,
            amount_limit=Decimal("1000000.0000"),
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 12, 31),
        )

    def create_purchase_request(
        self,
        agreement: SupplierAgreement | None = None,
    ) -> PurchaseRequest:
        return PurchaseRequest.objects.create(
            project_id=uuid4(),
            specification_version_id=uuid4(),
            requested_by=uuid4(),
            supplier_agreement=agreement,
        )

    def test_supplier_code_must_be_unique(self) -> None:
        self.create_supplier(code="SUP-DUP")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_supplier(code="SUP-DUP")

    def test_supplier_bin_must_be_unique_per_company(self) -> None:
        company_id = uuid4()
        Supplier.objects.create(
            code="SUP-BIN-1",
            name="Supplier 1",
            company_id=company_id,
            bin="123456789012",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Supplier.objects.create(
                code="SUP-BIN-2",
                name="Supplier 2",
                company_id=company_id,
                bin="123456789012",
            )

    def test_supplier_agreement_number_must_be_unique_per_supplier(self) -> None:
        supplier = self.create_supplier()
        self.create_agreement(supplier=supplier, agreement_number="AGR-DUP")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_agreement(supplier=supplier, agreement_number="AGR-DUP")

    def test_supplier_contract_number_must_be_unique_per_supplier(self) -> None:
        supplier = self.create_supplier()
        self.create_agreement(
            supplier=supplier,
            agreement_number="AGR-1",
            contract_number="CN-1",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_agreement(
                supplier=supplier,
                agreement_number="AGR-2",
                contract_number="CN-1",
            )

    def test_supplier_agreement_valid_to_cannot_precede_valid_from(self) -> None:
        supplier = self.create_supplier()

        with self.assertRaises(IntegrityError), transaction.atomic():
            SupplierAgreement.objects.create(
                supplier=supplier,
                agreement_number="AGR-BAD-DATES",
                valid_from=date(2026, 2, 1),
                valid_to=date(2026, 1, 31),
            )

    def test_supplier_agreement_amount_limit_cannot_be_negative(self) -> None:
        supplier = self.create_supplier()

        with self.assertRaises(IntegrityError), transaction.atomic():
            SupplierAgreement.objects.create(
                supplier=supplier,
                agreement_number="AGR-BAD-AMOUNT",
                amount_limit=Decimal("-0.0001"),
                valid_from=date(2026, 1, 1),
            )

    def test_purchase_request_item_position_must_be_unique_per_request(self) -> None:
        purchase_request = self.create_purchase_request()
        self.create_item(purchase_request=purchase_request, position=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(purchase_request=purchase_request, position=1)

    def test_purchase_request_item_quantity_must_be_positive(self) -> None:
        purchase_request = self.create_purchase_request()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(
                purchase_request=purchase_request,
                quantity=Decimal("0.000000"),
            )

    def test_purchase_request_item_estimated_unit_price_cannot_be_negative(self) -> None:
        purchase_request = self.create_purchase_request()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(
                purchase_request=purchase_request,
                estimated_unit_price=Decimal("-0.0001"),
            )

    def test_purchase_request_item_budget_price_cannot_be_negative(self) -> None:
        purchase_request = self.create_purchase_request()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(
                purchase_request=purchase_request,
                budget_price=Decimal("-0.0001"),
            )

    def test_cross_service_identifiers_are_uuid_fields_without_foreign_keys(self) -> None:
        purchase_request_uuid_fields = (
            "company_id",
            "project_id",
            "specification_version_id",
            "requested_by",
        )
        item_uuid_fields = ("nomenclature_id", "unit_id")

        for field_name in purchase_request_uuid_fields:
            field = PurchaseRequest._meta.get_field(field_name)
            self.assertIsInstance(field, UUIDField)
            self.assertIsNone(field.remote_field)

        for field_name in item_uuid_fields:
            field = PurchaseRequestItem._meta.get_field(field_name)
            self.assertIsInstance(field, UUIDField)
            self.assertIsNone(field.remote_field)

    def test_intraservice_relationships_are_foreign_keys(self) -> None:
        self.assertIsInstance(SupplierAgreement._meta.get_field("supplier"), ForeignKey)
        self.assertIsInstance(
            PurchaseRequest._meta.get_field("supplier_agreement"),
            ForeignKey,
        )
        self.assertIsInstance(
            PurchaseRequestItem._meta.get_field("purchase_request"),
            ForeignKey,
        )

    def test_status_fields_use_text_choices(self) -> None:
        supplier_status = Supplier._meta.get_field("status")
        agreement_status = SupplierAgreement._meta.get_field("status")
        request_status = PurchaseRequest._meta.get_field("status")

        self.assertEqual(supplier_status.choices, Supplier.Status.choices)
        self.assertEqual(agreement_status.choices, SupplierAgreement.Status.choices)
        self.assertEqual(request_status.choices, PurchaseRequest.Status.choices)
        self.assertEqual(SupplierAgreement.Status.ACTIVE, "active")
        self.assertEqual(PurchaseRequest.Status.SUBMITTED, "submitted")

    def test_timestamps_are_timezone_aware(self) -> None:
        supplier = self.create_supplier()

        self.assertTrue(timezone.is_aware(supplier.created_at))
        self.assertTrue(timezone.is_aware(supplier.updated_at))

    def create_item(
        self,
        purchase_request: PurchaseRequest,
        position: int = 1,
        quantity: Decimal = Decimal("1.000000"),
        estimated_unit_price: Decimal = Decimal("10.0000"),
        budget_price: Decimal | None = None,
    ) -> PurchaseRequestItem:
        return PurchaseRequestItem.objects.create(
            purchase_request=purchase_request,
            position=position,
            nomenclature_id=uuid4(),
            unit_id=uuid4(),
            quantity=quantity,
            estimated_unit_price=estimated_unit_price,
            budget_price=budget_price,
        )
