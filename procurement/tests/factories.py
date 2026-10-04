from decimal import Decimal
from uuid import uuid4

from procurement.models import PurchaseRequest, PurchaseRequestItem, Supplier


def create_supplier(**overrides) -> Supplier:
    data = {"code": f"SUP-{uuid4()}", "name": "Test supplier"}
    return Supplier.objects.create(**(data | overrides))


def create_purchase_request(**overrides) -> PurchaseRequest:
    data = {
        "project_id": uuid4(),
        "specification_version_id": uuid4(),
        "requested_by": uuid4(),
    }
    return PurchaseRequest.objects.create(**(data | overrides))


def create_request_item(purchase_request, **overrides) -> PurchaseRequestItem:
    data = {
        "purchase_request": purchase_request,
        "position": 1,
        "nomenclature_id": uuid4(),
        "unit_id": uuid4(),
        "quantity": Decimal("2.000000"),
        "estimated_unit_price": Decimal("100.0000"),
    }
    return PurchaseRequestItem.objects.create(**(data | overrides))
