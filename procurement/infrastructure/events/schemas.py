"""Compatibility imports for versioned Procurement event schemas."""

from procurement.events.schemas import (
    CONSUMED_EVENT_FIELDS,
    PRODUCED_EVENT_FIELDS,
    ConsumedEvent,
    ConsumerEventName,
    ProcurementEvent,
    ProcurementEventName,
    validate_event_payload,
)

__all__ = [
    "CONSUMED_EVENT_FIELDS", "PRODUCED_EVENT_FIELDS", "ConsumedEvent",
    "ConsumerEventName", "ProcurementEvent", "ProcurementEventName", "validate_event_payload",
]
