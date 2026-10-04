import json
import logging
import re
from uuid import UUID

from django.utils import timezone


EVENT_FIELDS = ("event_id", "event_type", "correlation_id", "causation_id", "producer", "attempt", "result", "error")


def event_log_fields(event=None, *, attempt=0, result, error=None):
    event = event if isinstance(event, dict) else {}
    fields = {}
    for field in ("event_id", "correlation_id", "causation_id"):
        try:
            fields[field] = str(UUID(str(event.get(field)))) if event.get(field) is not None else None
        except (ValueError, TypeError, AttributeError):
            fields[field] = None
    # Do not echo arbitrary envelope text or exception messages into operational logs.
    for field in ("event_type", "producer"):
        value = event.get(field)
        fields[field] = value if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", value) else None
    fields.update(attempt=attempt, result=result, error=error)
    return fields


class EventJSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": timezone.now().isoformat(), "level": record.levelname, "logger": record.name,
            "message": record.getMessage(),
        }
        data.update({field: getattr(record, field, None) for field in EVENT_FIELDS})
        return json.dumps(data, ensure_ascii=True)
