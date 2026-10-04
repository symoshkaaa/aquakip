import json
import logging
import threading

from django.db import close_old_connections, connection, transaction

from procurement.events.consumers import CONSUMER_HANDLERS, dispatch_event
from procurement.events.envelope import validate_envelope
from procurement.events.logging import event_log_fields
from procurement.events.rabbitmq import ProcurementTopology, connect_rabbitmq

logger = logging.getLogger(__name__)


def _reject_json_constant(value):
    raise ValueError("Non-finite JSON number")


def process_delivery(channel, method, properties, body, *, attempt=1):
    if connection.in_atomic_block:
        raise RuntimeError("The transport must run outside database transactions")
    event = None
    try:
        event = json.loads(body, parse_constant=_reject_json_constant)
        validate_envelope(event, consumed=True)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        error = "invalid_envelope"
        if isinstance(event, dict):
            if type(event.get("event_version")) is not int or event.get("event_version") != 1:
                error = "unsupported_event_version"
            elif isinstance(event.get("event_type"), str) and event["event_type"] not in CONSUMER_HANDLERS:
                error = "unsupported_event_type"
        # Poison messages follow the finite quarantine chain; never call a handler.
        logger.warning("Envelope quarantined", extra=event_log_fields(
            event, attempt=attempt, result="dlq" if attempt == 4 else "quarantined",
            error=error,
        ))
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return "dlq" if attempt == 4 else "quarantined"
    try:
        # durable=True makes the outermost commit boundary explicit, including duplicates.
        with transaction.atomic(durable=True):
            processed = dispatch_event(event)
    except Exception as error:
        result = "dlq" if attempt == 4 else "retry"
        logger.warning("Inbox processing failed", extra=event_log_fields(
            event, attempt=attempt, result=result, error=type(error).__name__,
        ))
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return result
    channel.basic_ack(delivery_tag=method.delivery_tag)
    result = "processed" if processed else "duplicate"
    logger.info("Inbox delivery committed", extra=event_log_fields(event, attempt=attempt, result=result))
    return result


class ProcurementConsumer:
    def __init__(self, *, topology=None, connection_factory=connect_rabbitmq):
        self.topology = topology or ProcurementTopology.from_settings()
        self.connection_factory = connection_factory

    def run(self, *, stop_event=None, max_messages=None):
        stop_event = stop_event or threading.Event()
        delivered = 0
        reconnect_delay = 1
        while not stop_event.is_set():
            broker = None
            try:
                broker = self.connection_factory()
                channel = broker.channel()
                self.topology.declare(channel)
                channel.basic_qos(prefetch_count=1)

                def callback(attempt):
                    def consume(channel, method, properties, body):
                        nonlocal delivered
                        if stop_event.is_set():
                            return
                        close_old_connections()
                        try:
                            process_delivery(channel, method, properties, body, attempt=attempt)
                        finally:
                            close_old_connections()
                        delivered += 1
                        if max_messages is not None and delivered >= max_messages:
                            stop_event.set()
                    return consume

                for attempt, queue in enumerate(self.topology.work_queues, start=1):
                    channel.basic_consume(queue=queue, on_message_callback=callback(attempt), auto_ack=False)
                reconnect_delay = 1
                while not stop_event.is_set():
                    broker.process_data_events(time_limit=1)
            except Exception as error:
                from django.core.exceptions import ImproperlyConfigured

                if isinstance(error, ImproperlyConfigured):
                    raise
                logger.warning("Consumer connection interrupted", extra=event_log_fields(
                    result="reconnecting", error=type(error).__name__,
                ))
                if not stop_event.is_set():
                    stop_event.wait(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 30)
            finally:
                if broker is not None and broker.is_open:
                    try:
                        broker.close()
                    except Exception:
                        pass
                close_old_connections()
        return delivered
