import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Literal, TypedDict
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from procurement.models import AlternativeRequest, ExpectedDelivery, PurchaseOrder, RFQ, SupplierOffer


ProcurementEventName = Literal[
    "procurement.request_created", "procurement.rfq_created", "procurement.rfq_sent",
    "procurement.supplier_offer_received", "procurement.supplier_offer_verified",
    "procurement.comparison_created", "procurement.alternative_requested",
    "procurement.alternative_approved", "procurement.alternative_rejected",
    "procurement.purchase_order_created", "procurement.purchase_order_approved",
    "procurement.purchase_order_sent", "procurement.delivery_expected", "procurement.delivery_delayed",
]
ConsumerEventName = Literal[
    "project.activated", "engineering.specification_approved", "engineering.specification_changed",
    "warehouse.shortage_detected", "engineering.alternative_reviewed", "finance.expense_approved",
]


class EventEnvelope(TypedDict):
    event_id: str
    event_type: str
    event_version: int
    occurred_at: str
    correlation_id: str | None
    causation_id: str | None
    company_id: str | None
    project_id: str | None
    actor_id: str | None
    producer: str
    payload: dict[str, object]


ProcurementEvent = EventEnvelope
ConsumedEvent = EventEnvelope


def is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def is_aware_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = parse_datetime(value)
        return parsed is not None and timezone.is_aware(parsed)
    except ValueError:
        return False


def is_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def is_money(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        amount = Decimal(value)
        return amount.is_finite() and amount >= 0
    except InvalidOperation:
        return False


def is_currency(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) is not None


def choice(*values: str):
    return lambda value: isinstance(value, str) and value in values


@dataclass(frozen=True)
class EventSchema:
    aggregate_type: str
    fields: dict[str, Callable[[object], bool]]
    version: int = 1


_rfq = {"rfq_id": is_uuid, "purchase_request_id": is_uuid, "status": choice(*RFQ.Status.values)}
_offer = {"supplier_offer_id": is_uuid, "rfq_id": is_uuid, "supplier_id": is_uuid,
          "status": choice(*SupplierOffer.Status.values)}
_alternative_decision = {"alternative_request_id": is_uuid, "project_id": is_uuid,
                         "client_decision": choice("approved", "rejected"), "status": choice(*AlternativeRequest.Status.values)}
_delivery = {"expected_delivery_id": is_uuid, "purchase_order_id": is_uuid,
             "planned_date": is_date, "status": choice(*ExpectedDelivery.Status.values)}

PRODUCED_SCHEMAS: dict[str, EventSchema] = {
    "procurement.request_created": EventSchema("PurchaseRequest", {
        "purchase_request_id": is_uuid, "project_id": is_uuid, "specification_version_id": is_uuid,
    }),
    "procurement.rfq_created": EventSchema("RFQ", _rfq),
    "procurement.rfq_sent": EventSchema("RFQ", _rfq | {"updated_at": is_aware_datetime}),
    "procurement.supplier_offer_received": EventSchema("SupplierOffer", _offer),
    "procurement.supplier_offer_verified": EventSchema("SupplierOffer", _offer),
    "procurement.comparison_created": EventSchema("SupplierComparison", {
        "comparison_id": is_uuid, "purchase_request_id": is_uuid, "version": is_positive_integer,
    }),
    "procurement.alternative_requested": EventSchema("AlternativeRequest", {
        "alternative_request_id": is_uuid, "project_id": is_uuid, "request_item_id": is_uuid,
        "original_nomenclature_id": is_uuid, "alternative_nomenclature_id": is_uuid,
    }),
    "procurement.alternative_approved": EventSchema("AlternativeRequest", _alternative_decision),
    "procurement.alternative_rejected": EventSchema("AlternativeRequest", _alternative_decision),
    "procurement.purchase_order_created": EventSchema("PurchaseOrder", {
        "purchase_order_id": is_uuid, "project_id": is_uuid, "supplier_id": is_uuid,
        "number": is_text, "currency_code": is_currency, "total_amount": is_money,
    }),
    "procurement.purchase_order_approved": EventSchema("PurchaseOrder", {
        "purchase_order_id": is_uuid, "status": choice(*PurchaseOrder.Status.values), "approved_at": is_aware_datetime,
    }),
    "procurement.purchase_order_sent": EventSchema("PurchaseOrder", {
        "purchase_order_id": is_uuid, "status": choice(*PurchaseOrder.Status.values), "sent_at": is_aware_datetime,
    }),
    "procurement.delivery_expected": EventSchema("ExpectedDelivery", _delivery),
    "procurement.delivery_delayed": EventSchema("ExpectedDelivery", _delivery),
}

CONSUMED_SCHEMAS: dict[str, EventSchema] = {
    "project.activated": EventSchema("Project", {"project_id": is_uuid}),
    "engineering.specification_approved": EventSchema("SpecificationVersion", {"project_id": is_uuid, "specification_version_id": is_uuid}),
    "engineering.specification_changed": EventSchema("SpecificationVersion", {"project_id": is_uuid, "specification_version_id": is_uuid}),
    "warehouse.shortage_detected": EventSchema("Shortage", {"project_id": is_uuid, "nomenclature_id": is_uuid, "unit_id": is_uuid, "shortage_quantity": is_money}),
    "engineering.alternative_reviewed": EventSchema("AlternativeRequest", {"alternative_request_id": is_uuid, "technical_review_id": is_uuid, "decision": choice("approved", "rejected")}),
    "finance.expense_approved": EventSchema("Expense", {"project_id": is_uuid, "expense_id": is_uuid, "amount": is_money, "currency_code": is_currency}),
}

PRODUCED_EVENT_FIELDS = {name: frozenset(schema.fields) for name, schema in PRODUCED_SCHEMAS.items()}
CONSUMED_EVENT_FIELDS = {name: frozenset(schema.fields) for name, schema in CONSUMED_SCHEMAS.items()}


def validate_event_payload(event_type: str, payload: dict[str, object], *, event_version: int = 1, consumed: bool = False) -> EventSchema:
    schema = (CONSUMED_SCHEMAS if consumed else PRODUCED_SCHEMAS).get(event_type)
    if schema is None:
        raise ValueError(f"Unsupported procurement event: {event_type}")
    if type(event_version) is not int or event_version != schema.version:
        raise ValueError(f"Unsupported version for {event_type}")
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be an object")
    missing = schema.fields.keys() - payload.keys()
    if missing:
        raise ValueError(f"Missing fields for {event_type}: {', '.join(sorted(missing))}")
    if not consumed and payload.keys() - schema.fields.keys():
        raise ValueError(f"Unexpected fields for {event_type}")
    for field, validator in schema.fields.items():
        if not validator(payload[field]):
            raise ValueError(f"Invalid {field} for {event_type}")
    return schema
