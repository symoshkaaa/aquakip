import importlib
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from procurement.events.consumers import CONSUMER_HANDLERS


def connect_rabbitmq(url=None):
    url = settings.RABBITMQ_URL if url is None else url
    try:
        parsed = urlsplit(url or "")
        valid = parsed.scheme in ("amqp", "amqps") and bool(parsed.hostname)
    except ValueError:
        valid = False
    if not valid:
        raise ImproperlyConfigured("Set a valid RABBITMQ_URL (AMQP or AMQPS)")
    try:
        pika = importlib.import_module("pika")
    except ImportError:
        raise ImproperlyConfigured("Install requirements-rabbitmq.txt") from None
    parameters = pika.URLParameters(url)
    parameters.socket_timeout = 5
    parameters.stack_timeout = 10
    parameters.blocked_connection_timeout = 10
    parameters.heartbeat = 30
    parameters.connection_attempts = 1
    return pika.BlockingConnection(parameters)


@dataclass(frozen=True)
class ProcurementTopology:
    domain_exchange: str = "domain.events"
    dead_exchange: str = "dead.letter"
    prefix: str = "procurement.events"
    retry_delays_ms: tuple[int, int, int] = (60_000, 300_000, 1_800_000)
    delivery_limit: int = 5

    def __post_init__(self):
        if not all((self.domain_exchange, self.dead_exchange, self.prefix)):
            raise ValueError("Topology names must not be empty")
        if len(self.retry_delays_ms) != 3 or any(type(delay) is not int or delay < 1 for delay in self.retry_delays_ms):
            raise ValueError("Exactly three positive retry delays are required")
        if type(self.delivery_limit) is not int or self.delivery_limit < 1:
            raise ValueError("Delivery limit must be positive")

    @classmethod
    def from_settings(cls):
        return cls(
            domain_exchange=settings.RABBITMQ_EXCHANGE_DOMAIN,
            dead_exchange=settings.RABBITMQ_EXCHANGE_DEAD,
            prefix=settings.RABBITMQ_PROCUREMENT_QUEUE,
        )

    @property
    def retry_exchange(self):
        return f"{self.prefix}.retry"

    @property
    def return_exchange(self):
        return f"{self.prefix}.retry.return"

    @property
    def work_queues(self):
        return (self.prefix, *(f"{self.prefix}.attempt-{attempt}" for attempt in (2, 3, 4)))

    @property
    def retry_queues(self):
        return tuple(f"{self.prefix}.retry.{step}" for step in ("1m", "5m", "30m"))

    @property
    def dlq(self):
        return f"{self.prefix}.dlq"

    @property
    def dead_key(self):
        return f"{self.prefix}.dead"

    def _dead_letter_arguments(self, exchange, routing_key):
        # Quorum queues retain dead letters until the next durable queue confirms.
        return {
            "x-queue-type": "quorum",
            "x-overflow": "reject-publish",
            "x-dead-letter-strategy": "at-least-once",
            "x-dead-letter-exchange": exchange,
            "x-dead-letter-routing-key": routing_key,
            "x-delivery-limit": self.delivery_limit,
        }

    def declare(self, channel):
        channel.exchange_declare(exchange=self.domain_exchange, exchange_type="topic", durable=True)
        channel.exchange_declare(exchange=self.dead_exchange, exchange_type="topic", durable=True)
        channel.exchange_declare(exchange=self.retry_exchange, exchange_type="direct", durable=True)
        channel.exchange_declare(exchange=self.return_exchange, exchange_type="direct", durable=True)
        channel.queue_declare(queue=self.dlq, durable=True, arguments={"x-queue-type": "quorum"})
        channel.queue_bind(queue=self.dlq, exchange=self.dead_exchange, routing_key=self.dead_key)
        for index, queue in enumerate(self.work_queues):
            final = index == 3
            channel.queue_declare(
                queue=queue, durable=True,
                arguments=self._dead_letter_arguments(
                    self.dead_exchange if final else self.retry_exchange,
                    self.dead_key if final else ("1m", "5m", "30m")[index],
                ),
            )
            if index:
                channel.queue_bind(queue=queue, exchange=self.return_exchange, routing_key=f"attempt-{index + 1}")
        for key in CONSUMER_HANDLERS:
            channel.queue_bind(queue=self.work_queues[0], exchange=self.domain_exchange, routing_key=key)
        for index, (queue, delay) in enumerate(zip(self.retry_queues, self.retry_delays_ms)):
            channel.queue_declare(
                queue=queue, durable=True,
                arguments=self._dead_letter_arguments(self.return_exchange, f"attempt-{index + 2}")
                | {"x-message-ttl": delay},
            )
            channel.queue_bind(queue=queue, exchange=self.retry_exchange, routing_key=("1m", "5m", "30m")[index])


def setup_topology(*, topology=None):
    connection = connect_rabbitmq()
    try:
        (topology or ProcurementTopology.from_settings()).declare(connection.channel())
    finally:
        if connection.is_open:
            connection.close()
