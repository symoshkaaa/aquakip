from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class EventContext:
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    company_id: UUID | None = None
    project_id: UUID | None = None
    actor_id: UUID | None = None


_current_context: ContextVar[EventContext] = ContextVar("procurement_event_context", default=EventContext())


def get_event_context() -> EventContext:
    return _current_context.get()


def optional_uuid(value: UUID | str | None) -> UUID | None:
    return None if value is None else UUID(str(value))


@contextmanager
def event_context(**values):
    token = _current_context.set(EventContext(**{key: optional_uuid(value) for key, value in values.items()}))
    try:
        yield _current_context.get()
    finally:
        _current_context.reset(token)


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            correlation_id = UUID(request.headers.get("X-Correlation-ID", ""))
        except (ValueError, TypeError, AttributeError):
            correlation_id = uuid4()
        request.correlation_id = correlation_id
        with event_context(correlation_id=correlation_id):
            response = self.get_response(request)
        response["X-Correlation-ID"] = str(correlation_id)
        return response
