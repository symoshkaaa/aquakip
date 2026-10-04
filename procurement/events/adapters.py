import importlib
import json
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class PublishNotConfirmed(Exception):
    pass


class BrokerAdapter(Protocol):
    def publish(self, *, event_type: str, body: bytes) -> bool:
        """Return True only after a positive broker confirmation."""
        ...

    def close(self) -> None: ...


@dataclass
class InMemoryAdapter:
    confirmed: bool = True
    messages: list[tuple[str, bytes]] = field(default_factory=list)

    def publish(self, *, event_type: str, body: bytes) -> bool:
        self.messages.append((event_type, body))
        return self.confirmed

    def close(self) -> None:
        pass


class RabbitMQAdapter:
    def __init__(self, *, url: str | None, exchange: str = "domain.events"):
        if not url:
            raise ImproperlyConfigured("RABBITMQ_URL is required for the outbox relay")
        try:
            parsed = urlsplit(url)
            valid_url = parsed.scheme in ("amqp", "amqps") and bool(parsed.hostname)
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ImproperlyConfigured("RABBITMQ_URL must be a valid AMQP or AMQPS URL")
        if not exchange:
            raise ImproperlyConfigured("RABBITMQ_EXCHANGE_DOMAIN must not be empty")
        self.url = url
        self.exchange = exchange
        self._connection = None
        self._channel = None
        self._pika = None

    def _connect(self):
        if self._connection and self._connection.is_open and self._channel and self._channel.is_open:
            return
        self.close()
        try:
            self._pika = importlib.import_module("pika")
        except ImportError as error:
            raise ImproperlyConfigured("Install requirements-rabbitmq.txt to run the relay") from error
        parameters = self._pika.URLParameters(self.url)
        parameters.socket_timeout = 10
        parameters.stack_timeout = 20
        parameters.blocked_connection_timeout = 20
        parameters.heartbeat = 30
        parameters.connection_attempts = 1
        self._connection = self._pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(exchange=self.exchange, exchange_type="topic", durable=True)
        self._channel.confirm_delivery()

    def publish(self, *, event_type: str, body: bytes) -> bool:
        try:
            self._connect()
            envelope = json.loads(body)
            result = self._channel.basic_publish(
                exchange=self.exchange, routing_key=event_type, body=body, mandatory=True,
                properties=self._pika.BasicProperties(
                    content_type="application/json", content_encoding="utf-8", delivery_mode=2,
                    message_id=envelope["event_id"], type=event_type, app_id=envelope["producer"],
                    correlation_id=envelope["correlation_id"],
                    headers={"event_version": envelope["event_version"], "causation_id": envelope["causation_id"]},
                ),
            )
            # BlockingChannel returns after confirm; NACK and unroutable messages raise.
            if result is False:
                raise PublishNotConfirmed("Broker did not confirm the message")
            return True
        except Exception:
            try:
                self.close()
            except Exception:
                pass
            raise

    def close(self) -> None:
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        finally:
            self._connection = None
            self._channel = None


def get_broker_adapter() -> BrokerAdapter:
    return RabbitMQAdapter(url=settings.RABBITMQ_URL, exchange=settings.RABBITMQ_EXCHANGE_DOMAIN)
