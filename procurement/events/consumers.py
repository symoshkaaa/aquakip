import logging
from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from procurement.events.context import event_context
from procurement.events.envelope import validate_envelope
from procurement.events.logging import event_log_fields
from procurement.events.schemas import ConsumedEvent
from procurement.models import InboxEvent

logger = logging.getLogger(__name__)


def _acknowledge_placeholder(event: ConsumedEvent) -> None:
    logger.info("Procurement subscription has no domain action yet", extra=event_log_fields(event, result="no_domain_action"))


def handle_project_activated(event: ConsumedEvent) -> None:
    # TODO: Define the procurement effect of project activation.
    _acknowledge_placeholder(event)


def handle_specification_approved(event: ConsumedEvent) -> None:
    # TODO: Define request creation and approval policy for an approved specification.
    _acknowledge_placeholder(event)


def handle_specification_changed(event: ConsumedEvent) -> None:
    # TODO: Define reconciliation of requests against changed specification versions.
    _acknowledge_placeholder(event)


def handle_warehouse_shortage_detected(event: ConsumedEvent) -> None:
    # TODO: Define shortage-to-purchase-request routing and quantities.
    _acknowledge_placeholder(event)


def handle_alternative_reviewed(event: ConsumedEvent) -> None:
    from procurement.services import record_alternative_technical_review

    record_alternative_technical_review(
        alternative_request_id=event["payload"]["alternative_request_id"],
        technical_review_id=event["payload"]["technical_review_id"],
        decision=event["payload"]["decision"],
    )


def handle_expense_approved(event: ConsumedEvent) -> None:
    # TODO: Define the relation between finance expenses and procurement approvals.
    _acknowledge_placeholder(event)


CONSUMER_HANDLERS: dict[str, Callable[[ConsumedEvent], None]] = {
    "project.activated": handle_project_activated,
    "engineering.specification_approved": handle_specification_approved,
    "engineering.specification_changed": handle_specification_changed,
    "warehouse.shortage_detected": handle_warehouse_shortage_detected,
    "engineering.alternative_reviewed": handle_alternative_reviewed,
    "finance.expense_approved": handle_expense_approved,
}


@transaction.atomic
def dispatch_event(event: ConsumedEvent) -> bool:
    validate_envelope(event, consumed=True)
    inbox, _ = InboxEvent.objects.get_or_create(
        event_id=event["event_id"],
        defaults={"producer": event["producer"], "event_type": event["event_type"]},
    )
    # The unique PK handles insert races; the lock serializes retries of existing rows.
    inbox = InboxEvent.objects.select_for_update().get(pk=inbox.pk)
    if inbox.producer != event["producer"] or inbox.event_type != event["event_type"]:
        raise ValueError("Event ID was reused by a different producer or event type")
    if inbox.status == InboxEvent.Status.PROCESSED:
        return False
    with event_context(
        correlation_id=event["correlation_id"] or event["event_id"], causation_id=event["event_id"],
        company_id=event["company_id"], project_id=event["project_id"], actor_id=event["actor_id"],
    ):
        CONSUMER_HANDLERS[event["event_type"]](event)
    inbox.status = InboxEvent.Status.PROCESSED
    inbox.processed_at = timezone.now()
    inbox.save(update_fields=("status", "processed_at"))
    return True
