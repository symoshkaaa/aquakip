import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from procurement.events.adapters import BrokerAdapter, PublishNotConfirmed, get_broker_adapter
from procurement.events.context import get_event_context, optional_uuid
from procurement.events.envelope import serialize_envelope
from procurement.events.logging import event_log_fields
from procurement.events.schemas import ProcurementEventName, validate_event_payload
from procurement.models import OutboxEvent

logger = logging.getLogger(__name__)


def enqueue_event(
    event_type: ProcurementEventName,
    aggregate_id: UUID | str,
    payload: dict[str, object],
    *,
    event_version: int = 1,
    company_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    actor_id: UUID | str | None = None,
) -> OutboxEvent:
    if not connection.in_atomic_block:
        raise RuntimeError("Outbox events must be written inside the business transaction")
    schema = validate_event_payload(event_type, payload, event_version=event_version)
    context = get_event_context()
    return OutboxEvent.objects.create(
        event_type=event_type, event_version=event_version,
        aggregate_type=schema.aggregate_type, aggregate_id=aggregate_id, payload=payload,
        correlation_id=context.correlation_id, causation_id=context.causation_id,
        company_id=optional_uuid(company_id) if company_id is not None else context.company_id,
        project_id=optional_uuid(project_id) if project_id is not None else context.project_id,
        actor_id=optional_uuid(actor_id) if actor_id is not None else context.actor_id,
    )


@dataclass(frozen=True)
class PublishResult:
    published: int
    failed: int


def publish_pending(*, adapter: BrokerAdapter | None = None, limit: int = 100) -> PublishResult:
    if connection.in_atomic_block:
        raise RuntimeError("Run the relay outside business transactions")
    if type(limit) is not int or limit < 1:
        raise ValueError("Outbox batch limit must be positive")
    owns_adapter = adapter is None
    adapter = get_broker_adapter() if adapter is None else adapter
    seen = []
    published = failed = 0
    try:
        for _ in range(limit):
            # The relay transaction owns only an outbox row, never a business write.
            with transaction.atomic():
                pending = OutboxEvent.objects.filter(published_at__isnull=True).exclude(pk__in=seen)
                if connection.features.has_select_for_update_skip_locked:
                    pending = pending.select_for_update(skip_locked=True)
                else:
                    pending = pending.select_for_update()
                event = pending.first()
                if event is None:
                    break
                seen.append(event.pk)
                event.attempts += 1
                error_code = None
                try:
                    if adapter.publish(event_type=event.event_type, body=serialize_envelope(event)) is not True:
                        raise PublishNotConfirmed("Broker did not confirm the message")
                except Exception as error:
                    failed += 1
                    error_code = type(error).__name__
                    event.save(update_fields=("attempts",))
                else:
                    event.published_at = timezone.now()
                    event.save(update_fields=("published_at", "attempts"))
                    published += 1
            # Report the outcome only after the relay transaction commits; never log exception text.
            log = logger.warning if error_code else logger.info
            log("Outbox publication failed" if error_code else "Outbox publication confirmed", extra=event_log_fields(
                {"event_id": event.event_id, "event_type": event.event_type,
                 "correlation_id": event.correlation_id, "causation_id": event.causation_id,
                 "producer": "procurement-service"}, attempt=event.attempts,
                result="publish_failed" if error_code else "published", error=error_code,
            ))
    finally:
        if owns_adapter:
            try:
                adapter.close()
            except Exception:
                logger.warning("Outbox adapter close failed")
    return PublishResult(published=published, failed=failed)
