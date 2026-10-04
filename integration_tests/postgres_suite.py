from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError, IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, tag

from procurement.events.consumers import CONSUMER_HANDLERS, dispatch_event
from procurement.events.publisher import publish_pending
from procurement.models import InboxEvent, OutboxEvent, PurchaseRequestItem, RFQ
from procurement.services import create_rfq
from procurement.tests.factories import create_purchase_request, create_request_item
from procurement.tests.test_events import incoming


@tag("integration", "postgresql")
class PostgreSQLTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql", "Use procurement_service.settings_integration")
        self.request = create_purchase_request()
        self.rfq = create_rfq(self.request)
        self.event = OutboxEvent.objects.get()

    def test_outbox_event_id_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutboxEvent.objects.create(
                event_id=self.event.event_id, event_type=self.event.event_type,
                aggregate_type="RFQ", aggregate_id=uuid4(), payload={},
            )

    def test_inbox_event_id_unique(self):
        event_id = uuid4()
        InboxEvent.objects.create(event_id=event_id, producer="project-service", event_type="project.activated")
        with self.assertRaises(IntegrityError), transaction.atomic():
            InboxEvent.objects.create(event_id=event_id, producer="project-service", event_type="project.activated")

    def test_business_and_outbox_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                create_rfq(self.request)
                raise RuntimeError("rollback")
        self.assertEqual(RFQ.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_consumer_rollback_includes_handler_outbox(self):
        def fail(event):
            create_rfq(self.request)
            raise TimeoutError()

        with patch.dict(CONSUMER_HANDLERS, {"project.activated": fail}), self.assertRaises(TimeoutError):
            dispatch_event(incoming())
        self.assertFalse(InboxEvent.objects.exists())
        self.assertEqual(RFQ.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_decimal_exact_roundtrip(self):
        item = create_request_item(self.request, quantity=Decimal("99999999999999.123456"), estimated_unit_price=Decimal("9999999999999999.1234"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("99999999999999.123456"))
        self.assertEqual(item.estimated_unit_price, Decimal("9999999999999999.1234"))

    def test_jsonfield_jsonb_and_nested_roundtrip(self):
        payload = {"nested": {"ids": [str(uuid4())], "nullable": None}, "amount": "12.1234"}
        OutboxEvent.objects.filter(pk=self.event.pk).update(payload=payload)
        self.event.refresh_from_db()
        self.assertEqual(self.event.payload, payload)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_typeof(payload)::text FROM procurement_outbox_event WHERE id = %s", [self.event.pk])
            self.assertEqual(cursor.fetchone()[0], "jsonb")

    def test_all_declared_indexes_and_constraints_exist(self):
        from django.apps import apps

        with connection.cursor() as cursor:
            for model in apps.get_app_config("procurement").get_models():
                actual = connection.introspection.get_constraints(cursor, model._meta.db_table)
                for declared in (*model._meta.indexes, *model._meta.constraints):
                    with self.subTest(model=model.__name__, name=declared.name):
                        self.assertIn(declared.name, actual)
                self.assertTrue(any(value["primary_key"] for value in actual.values()))
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'proc_outbox_pending_idx'")
            self.assertIn("WHERE (published_at IS NULL)", cursor.fetchone()[0])

    def test_database_check_constraints_are_enforced(self):
        item = create_request_item(self.request)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseRequestItem.objects.filter(pk=item.pk).update(quantity=Decimal("-1"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutboxEvent.objects.filter(pk=self.event.pk).update(event_version=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InboxEvent.objects.create(event_id=uuid4(), producer="project-service", event_type="project.activated", status="processed")

    def thread(self, action):
        close_old_connections()
        try:
            return action()
        finally:
            connections.close_all()

    def test_select_for_update_nowait_really_locks_row(self):
        def locked():
            with self.assertRaises(DatabaseError), transaction.atomic():
                OutboxEvent.objects.select_for_update(nowait=True).get(pk=self.event.pk)
            return True

        with transaction.atomic(), ThreadPoolExecutor(max_workers=1) as pool:
            OutboxEvent.objects.select_for_update().get(pk=self.event.pk)
            self.assertTrue(pool.submit(self.thread, locked).result(timeout=10))

    def test_relay_skip_locked_does_not_double_publish(self):
        started, release = Event(), Event()
        calls = []

        class Adapter:
            def publish(adapter, **kwargs):
                calls.append(kwargs)
                started.set()
                if not release.wait(10):
                    raise TimeoutError()
                return True

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.thread, lambda: publish_pending(adapter=Adapter()))
            try:
                self.assertTrue(started.wait(10))
                second = publish_pending(adapter=Adapter())
                self.assertEqual((second.published, second.failed), (0, 0))
            finally:
                release.set()
            self.assertEqual(first.result(timeout=10).published, 1)
        self.assertEqual(len(calls), 1)

    def test_concurrent_duplicate_inbox_has_one_business_effect(self):
        event = incoming()
        barrier = Barrier(2)
        effects = []

        def handler(event):
            effects.append(event["event_id"])
            create_rfq(self.request)

        def deliver():
            barrier.wait(timeout=10)
            return dispatch_event(event)

        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}), ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(self.thread, deliver) for _ in range(2)]
            self.assertEqual(sorted(result.result(timeout=15) for result in results), [False, True])
        self.assertEqual(len(effects), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(RFQ.objects.count(), 2)
        self.assertEqual(OutboxEvent.objects.count(), 2)
