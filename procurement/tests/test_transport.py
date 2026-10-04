import json
import logging
import threading
from io import StringIO
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection, transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from procurement.events.consumers import CONSUMER_HANDLERS
from procurement.events.health import procurement_readiness
from procurement.events.logging import EVENT_FIELDS, EventJSONFormatter, event_log_fields
from procurement.events.rabbitmq import ProcurementTopology, connect_rabbitmq
from procurement.events.transport import ProcurementConsumer, process_delivery
from procurement.models import InboxEvent, OutboxEvent, RFQ
from procurement.services import create_rfq
from procurement.tests.factories import create_purchase_request
from procurement.tests.test_events import incoming


class TopologyTests(SimpleTestCase):
    def setUp(self):
        self.topology = ProcurementTopology()
        self.channel = Mock()
        self.topology.declare(self.channel)

    def test_durable_exchanges(self):
        self.channel.exchange_declare.assert_any_call(exchange="domain.events", exchange_type="topic", durable=True)
        self.channel.exchange_declare.assert_any_call(exchange="dead.letter", exchange_type="topic", durable=True)

    def test_all_queues_durable_and_quorum(self):
        self.assertEqual(self.channel.queue_declare.call_count, 8)
        for call in self.channel.queue_declare.call_args_list:
            self.assertTrue(call.kwargs["durable"])
            self.assertEqual(call.kwargs["arguments"]["x-queue-type"], "quorum")

    def test_three_retry_ttls_and_return_routes(self):
        calls = {call.kwargs["queue"]: call.kwargs["arguments"] for call in self.channel.queue_declare.call_args_list}
        for index, (queue, ttl) in enumerate(zip(self.topology.retry_queues, (60_000, 300_000, 1_800_000))):
            self.assertEqual(calls[queue]["x-message-ttl"], ttl)
            self.assertEqual(calls[queue]["x-dead-letter-exchange"], self.topology.return_exchange)
            self.assertEqual(calls[queue]["x-dead-letter-routing-key"], f"attempt-{index + 2}")

    def test_final_attempt_routes_to_dlq_and_no_infinite_requeue(self):
        calls = {call.kwargs["queue"]: call.kwargs["arguments"] for call in self.channel.queue_declare.call_args_list}
        final = calls[self.topology.work_queues[-1]]
        self.assertEqual(final["x-dead-letter-exchange"], "dead.letter")
        self.assertEqual(final["x-dead-letter-routing-key"], self.topology.dead_key)
        for queue in (*self.topology.work_queues, *self.topology.retry_queues):
            self.assertEqual(calls[queue]["x-dead-letter-strategy"], "at-least-once")
            self.assertEqual(calls[queue]["x-overflow"], "reject-publish")
            self.assertEqual(calls[queue]["x-delivery-limit"], 5)

    def test_exactly_six_subscriptions_only_on_initial_queue(self):
        bindings = [call.kwargs for call in self.channel.queue_bind.call_args_list if call.kwargs["exchange"] == "domain.events"]
        self.assertEqual({binding["routing_key"] for binding in bindings}, set(CONSUMER_HANDLERS))
        self.assertTrue(all(binding["queue"] == self.topology.work_queues[0] for binding in bindings))

    def test_declarations_are_idempotent(self):
        calls = self.channel.mock_calls.copy()
        self.channel.reset_mock()
        self.topology.declare(self.channel)
        self.assertEqual(self.channel.mock_calls, calls)

    def test_invalid_topology_rejected(self):
        for values in ({"prefix": ""}, {"delivery_limit": -1}, {"retry_delays_ms": (0, 1, 2)}, {"retry_delays_ms": (1, 2)}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ProcurementTopology(**values)

    @override_settings(RABBITMQ_URL=None)
    def test_connection_is_opt_in_and_import_is_lazy(self):
        with patch("procurement.events.rabbitmq.importlib.import_module") as load:
            with self.assertRaises(ImproperlyConfigured):
                connect_rabbitmq()
        load.assert_not_called()

    def test_connection_parameters_have_bounded_timeouts(self):
        pika = Mock()
        with patch("procurement.events.rabbitmq.importlib.import_module", return_value=pika):
            connect_rabbitmq("amqp://user:password@localhost:5672/%2F")
        parameters = pika.URLParameters.return_value
        self.assertEqual(parameters.socket_timeout, 5)
        self.assertEqual(parameters.stack_timeout, 10)
        self.assertEqual(parameters.connection_attempts, 1)


class TransportTests(TransactionTestCase):
    def setUp(self):
        self.channel = Mock()
        self.method = Mock(delivery_tag=7)
        self.event = incoming()

    def deliver(self, event=None, *, attempt=1, body=None):
        return process_delivery(self.channel, self.method, Mock(), body or json.dumps(event or self.event).encode(), attempt=attempt)

    def test_ack_sees_committed_inbox_and_handler_effect(self):
        request = create_purchase_request()

        def ack(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(InboxEvent.objects.get().status, InboxEvent.Status.PROCESSED)
            self.assertEqual(RFQ.objects.count(), 1)
            self.assertEqual(OutboxEvent.objects.count(), 1)

        self.channel.basic_ack.side_effect = ack
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": lambda event: create_rfq(request)}):
            self.assertEqual(self.deliver(), "processed")
        self.channel.basic_ack.assert_called_once_with(delivery_tag=7)
        self.channel.basic_nack.assert_not_called()

    def test_duplicate_is_acknowledged_without_second_effect(self):
        handler = Mock()
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}):
            self.assertEqual(self.deliver(), "processed")
            self.assertEqual(self.deliver(), "duplicate")
        handler.assert_called_once()
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(self.channel.basic_ack.call_count, 2)

    def test_handler_failure_rolls_back_then_nacks_without_requeue(self):
        request = create_purchase_request()

        def fail(event):
            create_rfq(request)
            raise TimeoutError("secret AMQP URL must not appear")

        with patch.dict(CONSUMER_HANDLERS, {"project.activated": fail}), self.assertLogs("procurement.events.transport") as logs:
            self.assertEqual(self.deliver(), "retry")
        self.assertNotIn("secret", " ".join(logs.output))
        self.assertEqual(logs.records[0].error, "TimeoutError")
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(RFQ.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.channel.basic_ack.assert_not_called()
        self.channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)

    def test_last_failure_is_dlq(self):
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": Mock(side_effect=OperationalError())}):
            self.assertEqual(self.deliver(attempt=4), "dlq")
        self.channel.basic_ack.assert_not_called()
        self.channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)

    def test_commit_failure_does_not_ack(self):
        with patch.object(connection, "commit", side_effect=OperationalError("commit failed")):
            self.assertEqual(self.deliver(), "retry")
        self.channel.basic_ack.assert_not_called()
        self.assertFalse(InboxEvent.objects.exists())

    def test_unknown_version_never_invokes_handler_or_ack(self):
        handler = Mock()
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}), self.assertLogs("procurement.events.transport") as logs:
            self.assertEqual(self.deliver(self.event | {"event_version": 2}), "quarantined")
        self.assertEqual(logs.records[0].error, "unsupported_event_version")
        handler.assert_not_called()
        self.channel.basic_ack.assert_not_called()
        self.assertFalse(InboxEvent.objects.exists())

    def test_unknown_type_is_quarantined(self):
        self.assertEqual(self.deliver(self.event | {"event_type": "unknown.event"}), "quarantined")
        self.channel.basic_ack.assert_not_called()

    def test_malformed_messages_do_not_kill_next_delivery(self):
        for body in (b"not json", b"\xff", b"[]", b'{"value":NaN}'):
            with self.subTest(body=body):
                self.assertEqual(self.deliver(body=body), "quarantined")
        self.assertEqual(self.deliver(), "processed")
        self.assertEqual(self.channel.basic_nack.call_count, 4)
        self.channel.basic_ack.assert_called_once()

    def test_outer_transaction_is_rejected_before_any_ack(self):
        with transaction.atomic(), self.assertRaises(RuntimeError):
            self.deliver()
        self.channel.basic_ack.assert_not_called()
        self.channel.basic_nack.assert_not_called()

    def test_ack_failure_does_not_roll_back_committed_business_effect(self):
        self.channel.basic_ack.side_effect = ConnectionError()
        with self.assertRaises(ConnectionError):
            self.deliver()
        self.assertEqual(InboxEvent.objects.get().status, InboxEvent.Status.PROCESSED)
        self.channel.basic_ack.side_effect = None
        self.assertEqual(self.deliver(), "duplicate")


class RunnerTests(SimpleTestCase):
    def test_real_runner_uses_manual_ack_and_all_four_attempt_queues(self):
        broker = Mock()
        stop = threading.Event()
        broker.process_data_events.side_effect = lambda **kwargs: stop.set()
        runner = ProcurementConsumer(connection_factory=lambda: broker)
        self.assertEqual(runner.run(stop_event=stop), 0)
        channel = broker.channel.return_value
        self.assertEqual(channel.basic_consume.call_count, 4)
        self.assertTrue(all(call.kwargs["auto_ack"] is False for call in channel.basic_consume.call_args_list))
        broker.close.assert_called_once()

    def test_reconnect_logs_no_connection_secrets(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        with self.assertLogs("procurement.events.transport") as logs:
            ProcurementConsumer(connection_factory=Mock(side_effect=ConnectionError("amqp://secret"))).run(stop_event=stop)
        self.assertNotIn("secret", " ".join(logs.output))
        stop.wait.assert_called_once_with(1)

    @override_settings(RABBITMQ_URL=None)
    def test_commands_unconfigured_and_invalid_limit_fail_cleanly(self):
        for command in ("setup_procurement_rabbitmq", "consume_procurement_events"):
            with self.subTest(command=command), self.assertRaises(CommandError):
                call_command(command)
        with self.assertRaises(CommandError):
            call_command("consume_procurement_events", max_messages=0)

    def test_setup_command_calls_topology(self):
        with patch("procurement.management.commands.setup_procurement_rabbitmq.setup_topology") as setup:
            call_command("setup_procurement_rabbitmq", stdout=StringIO())
        setup.assert_called_once()

    def test_json_logging_has_required_fields_and_sanitizes_poison_metadata(self):
        event = incoming(producer="amqp://user:password@broker")
        fields = event_log_fields(event, attempt=2, result="quarantined", error="invalid_envelope")
        record = logging.makeLogRecord({"msg": "Envelope quarantined", "levelname": "WARNING", **fields})
        output = EventJSONFormatter().format(record)
        self.assertTrue(set(EVENT_FIELDS) <= json.loads(output).keys())
        self.assertNotIn("password", output)


@override_settings(RABBITMQ_URL=None)
class ReadinessTests(TransactionTestCase):
    def test_demo_readiness_does_not_connect_to_broker(self):
        with patch("procurement.events.health.connect_rabbitmq") as connect:
            result = procurement_readiness()
        self.assertTrue(result["ready"])
        self.assertFalse(result["rabbitmq"]["enabled"])
        connect.assert_not_called()

    @override_settings(RABBITMQ_URL="amqp://user:secret@localhost")
    def test_transient_failure_is_unready_not_startup_error(self):
        with patch("procurement.events.health.connect_rabbitmq", side_effect=ConnectionError("secret")):
            result = procurement_readiness()
        self.assertFalse(result["ready"])
        self.assertNotIn("secret", json.dumps(result))

    @override_settings(RABBITMQ_URL="amqp://localhost")
    def test_both_dependencies_reachable(self):
        with patch("procurement.events.health.connect_rabbitmq") as connect:
            result = procurement_readiness()
        self.assertTrue(result["ready"])
        self.assertTrue(result["rabbitmq"]["reachable"])
        connect.return_value.close.assert_called_once()

    def test_db_failure_is_unready(self):
        with patch.object(connection, "cursor", side_effect=OperationalError()):
            self.assertFalse(procurement_readiness()["ready"])

    def test_readiness_command_json(self):
        output = StringIO()
        call_command("check_procurement_readiness", stdout=output)
        self.assertTrue(json.loads(output.getvalue())["ready"])
