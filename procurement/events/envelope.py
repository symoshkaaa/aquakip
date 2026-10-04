import json

from procurement.events.schemas import EventEnvelope, is_aware_datetime, is_uuid, validate_event_payload
from procurement.models import OutboxEvent


PRODUCER = "procurement-service"
_UUID_FIELDS = ("correlation_id", "causation_id", "company_id", "project_id", "actor_id")


def build_envelope(event: OutboxEvent) -> EventEnvelope:
    return {
        "event_id": str(event.event_id), "event_type": event.event_type, "event_version": event.event_version,
        "occurred_at": event.created_at.isoformat().replace("+00:00", "Z"),
        **{field: str(getattr(event, field)) if getattr(event, field) else None for field in _UUID_FIELDS},
        "producer": PRODUCER, "payload": event.payload,
    }


def validate_envelope(event: object, *, consumed: bool = False) -> None:
    if not isinstance(event, dict):
        raise ValueError("Event envelope must be an object")
    required = {"event_id", "event_type", "event_version", "occurred_at", "producer", "payload", *_UUID_FIELDS}
    if required - event.keys():
        raise ValueError("Incomplete event envelope")
    if not is_uuid(event["event_id"]) or not is_aware_datetime(event["occurred_at"]):
        raise ValueError("Invalid event ID or timestamp")
    if not isinstance(event["producer"], str) or not event["producer"].strip() or len(event["producer"]) > 64:
        raise ValueError("Invalid event producer")
    if not isinstance(event["event_type"], str):
        raise ValueError("Invalid event type")
    for field in _UUID_FIELDS:
        if event[field] is not None and not is_uuid(event[field]):
            raise ValueError(f"Invalid {field}")
    if not consumed and event["producer"] != PRODUCER:
        raise ValueError("Invalid Procurement producer")
    validate_event_payload(event["event_type"], event["payload"], event_version=event["event_version"], consumed=consumed)


def serialize_envelope(event: OutboxEvent) -> bytes:
    envelope = build_envelope(event)
    validate_envelope(envelope)
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
