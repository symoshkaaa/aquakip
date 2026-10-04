"""Compatibility imports for the transactional Inbox dispatcher."""

from procurement.events.consumers import (
    CONSUMER_HANDLERS,
    dispatch_event,
    handle_alternative_reviewed,
    handle_expense_approved,
    handle_project_activated,
    handle_specification_approved,
    handle_specification_changed,
    handle_warehouse_shortage_detected,
)

__all__ = [
    "CONSUMER_HANDLERS", "dispatch_event", "handle_alternative_reviewed",
    "handle_expense_approved", "handle_project_activated", "handle_specification_approved",
    "handle_specification_changed", "handle_warehouse_shortage_detected",
]
