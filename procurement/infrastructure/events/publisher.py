"""Compatibility import: business event calls now enqueue, never publish inline."""

from procurement.events.publisher import enqueue_event as publish_event

__all__ = ["publish_event"]
