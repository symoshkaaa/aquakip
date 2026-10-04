import json
import time
from threading import Event, Thread
from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings, tag

from procurement.events.adapters import RabbitMQAdapter
from procurement.events.consumers import CONSUMER_HANDLERS
from procurement.events.health import procurement_readiness
from procurement.events.publisher import publish_pending
from procurement.events.rabbitmq import ProcurementTopology, connect_rabbitmq
from procurement.events.transport import ProcurementConsumer, process_delivery
from procurement.models import AlternativeRequest, InboxEvent, OutboxEvent, RFQ
from procurement.services import create_alternative_request, create_rfq
from procurement.tests.factories import create_purchase_request, create_request_item
from procurement.tests.test_events import incoming


@tag("integration", "rabbitmq")
class RabbitMQTests(TransactionTestCase):
    def setUp(self):
        import pika

        self.assertEqual(connection.vendor, "postgresql", "Use integration settings and a real PostgreSQL database")
        self.pika = pika
        namespace = f"aquakip.integration.{uuid4().hex}"
        self.topology = ProcurementTopology(
            domain_exchange=f"{namespace}.domain", dead_exchange=f"{namespace}.dead",
            prefix=namespace, retry_delays_ms=(100, 200, 300),
        )
        self.broker = connect_rabbitmq()
        self.channel = self.broker.channel()
        self.topology.declare(self.channel)
        self.channel.confirm_delivery()
        self.request = create_purchase_request()
        self.stop = Event()
        self.worker = None

    def tearDown(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=15)
            self.assertFalse(self.worker.is_alive(), "Consumer did not stop")
        if self.broker.is_open:
            if not self.channel.is_open:
                self.channel = self.broker.channel()
            for queue in (*self.topology.work_queues, *self.topology.retry_queues, self.topology.dlq):
                self.channel.queue_delete(queue=queue)
            for exchange in (self.topology.domain_exchange, self.topology.dead_exchange, self.topology.retry_exchange, self.topology.return_exchange):
                self.channel.exchange_delete(exchange=exchange)
            self.broker.close()

    def send(self, event, *, body=None):
        self.channel.basic_publish(
            exchange=self.topology.domain_exchange, routing_key=event["event_type"] if event else "project.activated", mandatory=True,
            body=body if body is not None else json.dumps(event).encode(),
            properties=self.pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )

    def get(self, queue, *, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            method, properties, body = self.channel.basic_get(queue=queue, auto_ack=False)
            if method:
                return method, properties, body
            time.sleep(0.03)
        self.fail(f"No message in integration queue {queue}")

    def deliver(self, queue=None, *, attempt=1):
        method, properties, body = self.get(queue or self.topology.work_queues[0])
        return process_delivery(self.channel, method, properties, body, attempt=attempt)

    def empty(self, queue):
        method, _, _ = self.channel.basic_get(queue=queue, auto_ack=False)
        self.assertIsNone(method)

    def test_a_business_outbox_confirm_and_published_at(self):
        create_rfq(self.request)
        create_rfq(self.request)
        outbound = f"{self.topology.prefix}.outbound"
        self.channel.queue_declare(queue=outbound, durable=True, arguments={"x-queue-type": "quorum"})
        self.channel.queue_bind(queue=outbound, exchange=self.topology.domain_exchange, routing_key="procurement.#")
        adapter = RabbitMQAdapter(url=settings.RABBITMQ_URL, exchange=self.topology.domain_exchange)
        try:
            self.assertEqual(publish_pending(adapter=adapter, limit=1).published, 1)
            self.assertEqual(OutboxEvent.objects.filter(published_at__isnull=True).count(), 1)
            self.assertEqual(publish_pending(adapter=adapter, limit=1).published, 1)
            delivered_ids = set()
            for _ in range(2):
                method, properties, body = self.get(outbound)
                row = OutboxEvent.objects.get(event_id=json.loads(body)["event_id"])
                self.assertIsNotNone(row.published_at)
                delivered_ids.add(row.event_id)
                self.assertEqual(method.routing_key, row.event_type)
                self.assertEqual(properties.delivery_mode, 2)
                self.channel.basic_ack(delivery_tag=method.delivery_tag)
            self.assertEqual(len(delivered_ids), 2)
            self.assertEqual(publish_pending(adapter=adapter).published, 0)
            self.empty(outbound)
        finally:
            adapter.close()
            self.channel.queue_delete(queue=outbound)

    def test_b_inbound_inbox_handler_and_actual_ack(self):
        event = incoming()
        self.send(event)
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": lambda event: create_rfq(self.request)}):
            self.assertEqual(self.deliver(), "processed")
        self.assertEqual(InboxEvent.objects.get(pk=event["event_id"]).status, InboxEvent.Status.PROCESSED)
        self.assertEqual(RFQ.objects.count(), 1)
        # Closing the delivery channel would requeue any unacknowledged message.
        self.channel.close()
        self.channel = self.broker.channel()
        self.empty(self.topology.work_queues[0])

    def test_c_duplicate_event_id_has_no_duplicate_effect(self):
        event = incoming()
        self.send(event)
        self.send(event)
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": lambda event: create_rfq(self.request)}):
            self.assertEqual(self.deliver(), "processed")
            self.assertEqual(self.deliver(), "duplicate")
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(RFQ.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_d_temporary_failure_goes_through_ttl_retry(self):
        event = incoming()
        self.send(event)
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": Mock(side_effect=TimeoutError())}):
            self.assertEqual(self.deliver(), "retry")
        self.assertFalse(InboxEvent.objects.exists())
        method, properties, body = self.get(self.topology.work_queues[1])
        self.assertEqual(json.loads(body), event)
        self.assertTrue(any(death["reason"] == "expired" for death in properties.headers["x-death"]))
        self.assertEqual(process_delivery(self.channel, method, properties, body, attempt=2), "processed")
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.empty(self.topology.dlq)

    def test_e_exhausted_four_attempts_go_to_dlq(self):
        event = incoming()
        self.send(event)
        handler = Mock(side_effect=TimeoutError())
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}):
            for attempt, queue in enumerate(self.topology.work_queues, start=1):
                self.assertEqual(self.deliver(queue, attempt=attempt), "dlq" if attempt == 4 else "retry")
        method, properties, body = self.get(self.topology.dlq)
        self.assertEqual(json.loads(body), event)
        self.assertEqual(handler.call_count, 4)
        self.assertFalse(InboxEvent.objects.exists())
        self.channel.basic_ack(delivery_tag=method.delivery_tag)
        for queue in (*self.topology.work_queues, *self.topology.retry_queues):
            self.empty(queue)

    def test_f_real_broker_connection_failure_keeps_outbox_pending(self):
        create_rfq(self.request)
        adapter = RabbitMQAdapter(url="amqp://127.0.0.1:1/%2F", exchange=self.topology.domain_exchange)
        try:
            self.assertEqual(publish_pending(adapter=adapter).failed, 1)
        finally:
            adapter.close()
        row = OutboxEvent.objects.get()
        self.assertIsNone(row.published_at)
        self.assertEqual(row.attempts, 1)

    def test_unroutable_mandatory_publication_remains_pending(self):
        create_rfq(self.request)
        adapter = RabbitMQAdapter(url=settings.RABBITMQ_URL, exchange=self.topology.domain_exchange)
        try:
            self.assertEqual(publish_pending(adapter=adapter).failed, 1)
        finally:
            adapter.close()
        self.assertIsNone(OutboxEvent.objects.get().published_at)

    def test_unsupported_version_quarantine_reaches_dlq_without_handler(self):
        event = incoming(event_version=2)
        self.send(event)
        handler = Mock()
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}):
            for attempt, queue in enumerate(self.topology.work_queues, start=1):
                self.assertEqual(self.deliver(queue, attempt=attempt), "dlq" if attempt == 4 else "quarantined")
        method, _, body = self.get(self.topology.dlq)
        self.assertEqual(json.loads(body), event)
        self.channel.basic_ack(delivery_tag=method.delivery_tag)
        handler.assert_not_called()
        self.assertFalse(InboxEvent.objects.exists())

    def test_malformed_message_does_not_stop_consumer_transport(self):
        self.send(None, body=b"malformed")
        self.send(incoming())
        self.assertEqual(self.deliver(), "quarantined")
        self.assertEqual(self.deliver(), "processed")

    def test_real_consumer_runner_commits_and_stops_gracefully(self):
        event = incoming()
        self.send(event)
        errors = []

        def run():
            try:
                ProcurementConsumer(topology=self.topology).run(stop_event=self.stop, max_messages=1)
            except Exception as error:
                errors.append(type(error).__name__)

        self.worker = Thread(target=run, daemon=True)
        self.worker.start()
        self.worker.join(timeout=15)
        self.assertFalse(self.worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(InboxEvent.objects.get(pk=event["event_id"]).status, InboxEvent.Status.PROCESSED)
        self.empty(self.topology.work_queues[0])

    def test_setup_command_idempotent_on_real_broker(self):
        from io import StringIO

        with override_settings(
            RABBITMQ_EXCHANGE_DOMAIN=self.topology.domain_exchange,
            RABBITMQ_EXCHANGE_DEAD=self.topology.dead_exchange,
            RABBITMQ_PROCUREMENT_QUEUE=self.topology.prefix,
        ):
            # Setup command uses production TTLs, so use a separate isolated prefix.
            production = ProcurementTopology.from_settings()
            production = ProcurementTopology(domain_exchange=production.domain_exchange, dead_exchange=production.dead_exchange, prefix=f"{production.prefix}.production")
            with override_settings(RABBITMQ_PROCUREMENT_QUEUE=production.prefix):
                try:
                    call_command("setup_procurement_rabbitmq", stdout=StringIO())
                    call_command("setup_procurement_rabbitmq", stdout=StringIO())
                    for queue in (*production.work_queues, *production.retry_queues, production.dlq):
                        self.channel.queue_declare(queue=queue, passive=True)
                finally:
                    for queue in (*production.work_queues, *production.retry_queues, production.dlq):
                        self.channel.queue_delete(queue=queue)
                    for exchange in (production.retry_exchange, production.return_exchange):
                        self.channel.exchange_delete(exchange=exchange)

    def test_real_readiness_checks_both_dependencies(self):
        result = procurement_readiness()
        self.assertTrue(result["ready"])
        self.assertTrue(result["rabbitmq"]["reachable"])

    def test_actual_alternative_handler_business_transition(self):
        item = create_request_item(self.request)
        alternative = create_alternative_request(
            project_id=self.request.project_id, request_item=item,
            original_nomenclature_id=item.nomenclature_id, alternative_nomenclature_id=uuid4(),
        )
        event = incoming("engineering.alternative_reviewed", {
            "alternative_request_id": str(alternative.pk), "technical_review_id": str(uuid4()), "decision": "approved",
        }, producer="engineering-service")
        self.send(event)
        self.assertEqual(self.deliver(), "processed")
        alternative.refresh_from_db()
        self.assertEqual(alternative.status, AlternativeRequest.Status.TECHNICALLY_APPROVED)
        self.assertEqual(str(alternative.technical_review_id), event["payload"]["technical_review_id"])
        self.send(event)
        self.assertEqual(self.deliver(), "duplicate")

    def test_dead_letter_target_outage_retains_message_until_restored(self):
        event = incoming()
        self.send(event)
        # No destination exists when NACK is issued: ordinary DLX forwarding would lose this event.
        self.channel.queue_delete(queue=self.topology.retry_queues[0])
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": Mock(side_effect=TimeoutError())}):
            self.assertEqual(self.deliver(), "retry")
        self.broker.process_data_events(time_limit=0.2)
        self.topology.declare(self.channel)
        # RabbitMQ's internal dead-letter forwarding retry defaults to three minutes.
        method, properties, body = self.get(self.topology.work_queues[1], timeout=210)
        self.assertEqual(json.loads(body), event)
        self.assertEqual(process_delivery(self.channel, method, properties, body, attempt=2), "processed")
