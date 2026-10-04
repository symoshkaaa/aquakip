import json
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, models, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from procurement.events.adapters import InMemoryAdapter, RabbitMQAdapter
from procurement.events.consumers import CONSUMER_HANDLERS, dispatch_event
from procurement.events.context import event_context, get_event_context
from procurement.events.envelope import build_envelope, serialize_envelope, validate_envelope
from procurement.events.publisher import enqueue_event, publish_pending
from procurement.events.schemas import CONSUMED_SCHEMAS, PRODUCED_SCHEMAS, validate_event_payload
from procurement.models import (
    AlternativeRequest, ExpectedDelivery, InboxEvent, OutboxEvent,
    PurchaseOrder, PurchaseRequest, RFQ, SupplierOffer,
)
from procurement.services import (
    approve_purchase_order, create_alternative_request, create_purchase_order,
    create_purchase_request, create_rfq, create_supplier_comparison, mark_purchase_order_sent,
    mark_rfq_sent, record_alternative_client_decision, record_alternative_technical_review,
    record_expected_delivery, register_supplier_offer, verify_supplier_offer,
)
from procurement.tests.factories import (
    create_purchase_request as request_factory, create_request_item, create_supplier,
)


def incoming(event_type="project.activated", payload=None, **overrides):
    return {
        "event_id": str(uuid4()), "event_type": event_type, "event_version": 1,
        "occurred_at": timezone.now().isoformat(), "producer": "project-service",
        "correlation_id": None, "causation_id": None, "company_id": None,
        "project_id": None, "actor_id": None,
        "payload": {"project_id": str(uuid4())} if payload is None else payload,
    } | overrides


class EventServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.supplier = create_supplier()
        cls.request = request_factory()
        cls.item = create_request_item(cls.request)

    def event(self, name, record):
        event = OutboxEvent.objects.get(event_type=name, aggregate_id=record.pk)
        self.assertEqual(event.aggregate_type, PRODUCED_SCHEMAS[name].aggregate_type)
        self.assertIsNone(event.published_at)
        self.assertEqual(event.attempts, 0)
        self.assertTrue(timezone.is_aware(event.created_at))
        validate_envelope(build_envelope(event))
        return event

    def order(self, **overrides):
        return create_purchase_order(**({
            "project_id": self.request.project_id, "supplier": self.supplier,
            "number": "PO-EVENT", "currency_code": "KZT",
            "items": [{"nomenclature_id": self.item.nomenclature_id, "quantity": Decimal("2"), "unit_price": Decimal("10.1234")}],
        } | overrides))

    def alternative(self):
        return create_alternative_request(
            project_id=self.request.project_id, request_item=self.item,
            original_nomenclature_id=self.item.nomenclature_id, alternative_nomenclature_id=uuid4(),
        )

    def test_request_created_payload_and_model_metadata(self):
        record = create_purchase_request(
            project_id=uuid4(), specification_version_id=uuid4(), requested_by=uuid4(),
            items=[{"nomenclature_id": uuid4(), "unit_id": uuid4(), "quantity": Decimal("2.000001")}],
        )
        event = self.event("procurement.request_created", record)
        self.assertEqual(event.payload, {
            "purchase_request_id": str(record.pk), "project_id": str(record.project_id),
            "specification_version_id": str(record.specification_version_id),
        })
        self.assertEqual(event.company_id, record.company_id)
        self.assertEqual(event.project_id, record.project_id)
        self.assertEqual(event.actor_id, record.requested_by)
        self.assertEqual(record.items.count(), 1)

    def test_rfq_creation_and_send_use_actual_fields(self):
        rfq = create_rfq(self.request)
        created = self.event("procurement.rfq_created", rfq)
        self.assertEqual(created.payload["status"], RFQ.Status.DRAFT)
        sent = mark_rfq_sent(rfq)
        event = self.event("procurement.rfq_sent", sent)
        self.assertEqual(event.payload, {
            "rfq_id": str(rfq.pk), "purchase_request_id": str(self.request.pk),
            "status": RFQ.Status.OPEN, "updated_at": sent.updated_at.isoformat(),
        })
        self.assertEqual(event.company_id, self.request.company_id)
        self.assertEqual(event.project_id, self.request.project_id)
        with self.assertRaises(ValidationError):
            mark_rfq_sent(rfq)
        self.assertEqual(OutboxEvent.objects.filter(event_type="procurement.rfq_sent").count(), 1)

    def test_offer_registration_and_verification(self):
        offer = register_supplier_offer(
            create_rfq(self.request), self.supplier,
            {"offer_date": date(2026, 10, 4), "currency_code": "KZT"},
            [{"request_item": self.item, "nomenclature_id": self.item.nomenclature_id,
              "quantity": Decimal("2"), "unit_price": Decimal("10.1234")}],
        )
        event = self.event("procurement.supplier_offer_received", offer)
        self.assertEqual(event.payload["supplier_id"], str(self.supplier.pk))
        self.assertEqual(event.payload["rfq_id"], str(offer.rfq_id))
        self.assertEqual(event.payload["status"], SupplierOffer.Status.RECEIVED)
        verified = verify_supplier_offer(offer)
        event = self.event("procurement.supplier_offer_verified", verified)
        self.assertEqual(event.payload["status"], SupplierOffer.Status.VERIFIED)

    def test_comparison_created_payload(self):
        record = create_supplier_comparison(self.request, version=2, criteria={"price": 1})
        event = self.event("procurement.comparison_created", record)
        self.assertEqual(event.payload, {
            "comparison_id": str(record.pk), "purchase_request_id": str(self.request.pk), "version": 2,
        })

    def test_alternative_requested_and_client_decisions(self):
        for decision in ("approved", "rejected"):
            with self.subTest(decision=decision):
                alternative = self.alternative()
                event = self.event("procurement.alternative_requested", alternative)
                self.assertEqual(event.payload["request_item_id"], str(self.item.pk))
                self.assertEqual(event.payload["original_nomenclature_id"], str(self.item.nomenclature_id))
                self.assertEqual(event.payload["alternative_nomenclature_id"], str(alternative.alternative_nomenclature_id))
                record_alternative_technical_review(
                    alternative_request_id=alternative.pk, technical_review_id=uuid4(), decision="approved",
                )
                changed = record_alternative_client_decision(alternative, decision)
                event = self.event(f"procurement.alternative_{decision}", changed)
                self.assertEqual(event.payload["client_decision"], decision)
                self.assertEqual(event.payload["status"], changed.status)

    def test_order_create_approve_send_payloads_and_decimal(self):
        order = self.order()
        created = self.event("procurement.purchase_order_created", order)
        self.assertEqual(created.payload, {
            "purchase_order_id": str(order.pk), "project_id": str(order.project_id),
            "supplier_id": str(self.supplier.pk), "number": order.number,
            "currency_code": "KZT", "total_amount": "20.2468",
        })
        approved = approve_purchase_order(order)
        event = self.event("procurement.purchase_order_approved", approved)
        self.assertEqual(event.payload["approved_at"], approved.approved_at.isoformat())
        sent = mark_purchase_order_sent(order)
        event = self.event("procurement.purchase_order_sent", sent)
        self.assertEqual(event.payload["sent_at"], sent.sent_at.isoformat())
        self.assertEqual(event.project_id, order.project_id)

    def test_expected_and_delayed_delivery_events(self):
        order = self.order()
        for status in (ExpectedDelivery.Status.EXPECTED, ExpectedDelivery.Status.DELAYED):
            delivery = record_expected_delivery(purchase_order=order, planned_date=date(2026, 10, 10), status=status)
            event = self.event("procurement.delivery_expected", delivery)
            self.assertEqual(event.payload, {
                "expected_delivery_id": str(delivery.pk), "purchase_order_id": str(order.pk),
                "planned_date": "2026-10-10", "status": status,
            })
            self.assertEqual(event.project_id, order.project_id)
            if status == ExpectedDelivery.Status.DELAYED:
                self.event("procurement.delivery_delayed", delivery)
        self.assertEqual(OutboxEvent.objects.filter(event_type="procurement.delivery_delayed").count(), 1)

    def test_business_operation_never_gets_broker_adapter(self):
        with patch("procurement.events.publisher.get_broker_adapter") as factory:
            create_rfq(self.request)
            self.order()
        factory.assert_not_called()

    def test_outer_transaction_rollback_removes_business_and_outbox(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                create_rfq(self.request)
                self.assertEqual(OutboxEvent.objects.count(), 1)
                raise RuntimeError("rollback")
        self.assertFalse(RFQ.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_outbox_write_failure_rolls_back_business(self):
        with patch("procurement.events.publisher.OutboxEvent.objects.create", side_effect=DatabaseError("write failed")):
            with self.assertRaises(DatabaseError):
                create_rfq(self.request)
        self.assertFalse(RFQ.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_invalid_nested_request_rolls_back_outbox(self):
        before = PurchaseRequest.objects.count()
        with self.assertRaises(ValidationError):
            create_purchase_request(
                project_id=uuid4(), specification_version_id=uuid4(), requested_by=uuid4(),
                items=[{"nomenclature_id": uuid4(), "unit_id": uuid4(), "quantity": "1"},
                       {"nomenclature_id": uuid4(), "unit_id": uuid4(), "quantity": "-1"}],
            )
        self.assertEqual(PurchaseRequest.objects.count(), before)
        self.assertFalse(OutboxEvent.objects.exists())

    def test_schema_rejects_missing_fields_wrong_types_unknown_fields_and_versions(self):
        event = self.event("procurement.purchase_order_created", self.order())
        for payload, version in (
            (event.payload | {"total_amount": 20.2468}, 1),
            (event.payload | {"total_amount": "NaN"}, 1),
            (event.payload | {"supplier_id": "not-a-uuid"}, 1),
            (event.payload | {"invented_field": "x"}, 1),
            ({}, 1), (event.payload, 2), (event.payload, True),
        ):
            with self.subTest(payload=payload, version=version):
                with self.assertRaises(ValueError):
                    validate_event_payload(event.event_type, payload, event_version=version)
        self.assertEqual(len(PRODUCED_SCHEMAS), 14)

    def test_envelope_metadata_and_context_reset(self):
        correlation_id, causation_id = uuid4(), uuid4()
        with event_context(correlation_id=correlation_id, causation_id=causation_id):
            event = self.event("procurement.rfq_created", create_rfq(self.request))
        self.assertIsNone(get_event_context().correlation_id)
        envelope = json.loads(serialize_envelope(event))
        self.assertEqual(set(envelope), {
            "event_id", "event_type", "event_version", "occurred_at", "producer", "payload",
            "correlation_id", "causation_id", "company_id", "project_id", "actor_id",
        })
        self.assertEqual(envelope["producer"], "procurement-service")
        self.assertEqual(envelope["correlation_id"], str(correlation_id))
        self.assertEqual(envelope["causation_id"], str(causation_id))
        self.assertEqual(envelope["company_id"], str(self.request.company_id))
        self.assertIsNone(envelope["actor_id"])

    def test_event_ids_unique_and_external_metadata_are_uuids(self):
        event = self.event("procurement.rfq_created", create_rfq(self.request))
        self.assertIsInstance(event.pk, UUID)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutboxEvent.objects.create(
                event_id=event.event_id, event_type=event.event_type, aggregate_type="RFQ",
                aggregate_id=event.aggregate_id, payload=event.payload,
            )
        for name in ("aggregate_id", "correlation_id", "causation_id", "company_id", "project_id", "actor_id"):
            field = OutboxEvent._meta.get_field(name)
            self.assertIsInstance(field, models.UUIDField)
            self.assertFalse(field.is_relation)

    def test_database_rejects_nonpositive_event_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutboxEvent.objects.create(
                event_type="procurement.rfq_created", event_version=0,
                aggregate_type="RFQ", aggregate_id=uuid4(), payload={},
            )

    def test_database_rejects_incoherent_inbox_state(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            InboxEvent.objects.create(event_id=uuid4(), producer="project-service", event_type="project.activated", status="processed")


class OutboxRelayTests(TransactionTestCase):
    def setUp(self):
        self.request = request_factory()
        self.rfq = create_rfq(self.request)
        self.event = OutboxEvent.objects.get()

    def test_success_marks_published_only_after_confirmation(self):
        adapter = Mock()

        def confirm(**message):
            self.assertIsNone(OutboxEvent.objects.get(pk=self.event.pk).published_at)
            self.assertEqual(json.loads(message["body"])["event_id"], str(self.event.event_id))
            return True

        adapter.publish.side_effect = confirm
        result = publish_pending(adapter=adapter)
        self.event.refresh_from_db()
        self.assertEqual(result.published, 1)
        self.assertEqual(result.failed, 0)
        self.assertTrue(timezone.is_aware(self.event.published_at))
        self.assertEqual(self.event.attempts, 1)

    def test_failure_increases_attempts_and_keeps_pending_without_logging_secrets(self):
        adapter = Mock()
        adapter.publish.side_effect = ConnectionError("amqp://secret-password@broker")
        with self.assertLogs("procurement.events.publisher", level="WARNING") as logs:
            result = publish_pending(adapter=adapter)
        self.event.refresh_from_db()
        self.assertEqual(result.failed, 1)
        self.assertEqual(self.event.attempts, 1)
        self.assertIsNone(self.event.published_at)
        self.assertNotIn("secret-password", " ".join(logs.output))

    def test_negative_confirmation_does_not_mark_published(self):
        result = publish_pending(adapter=InMemoryAdapter(confirmed=False))
        self.event.refresh_from_db()
        self.assertEqual(result.failed, 1)
        self.assertIsNone(self.event.published_at)
        self.assertEqual(self.event.attempts, 1)

    def test_missing_confirmation_is_not_success(self):
        adapter = Mock()
        adapter.publish.return_value = None
        self.assertEqual(publish_pending(adapter=adapter).failed, 1)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.published_at)

    def test_retry_uses_identical_envelope_and_event_id(self):
        adapter = InMemoryAdapter(confirmed=False)
        publish_pending(adapter=adapter)
        adapter.confirmed = True
        self.assertEqual(publish_pending(adapter=adapter).published, 1)
        self.assertEqual(adapter.messages[0], adapter.messages[1])
        self.event.refresh_from_db()
        self.assertEqual(self.event.attempts, 2)

    def test_published_rows_are_not_sent_again(self):
        adapter = InMemoryAdapter()
        publish_pending(adapter=adapter)
        result = publish_pending(adapter=adapter)
        self.assertEqual(result.published, 0)
        self.assertEqual(len(adapter.messages), 1)

    def test_batch_limit(self):
        create_rfq(self.request)
        create_rfq(self.request)
        self.assertEqual(publish_pending(adapter=InMemoryAdapter(), limit=2).published, 2)
        self.assertEqual(OutboxEvent.objects.filter(published_at__isnull=True).count(), 1)

    def test_failed_row_is_attempted_once_per_batch_and_other_rows_continue(self):
        create_rfq(self.request)
        adapter = Mock()
        adapter.publish.side_effect = [ConnectionError("offline"), True]
        result = publish_pending(adapter=adapter, limit=10)
        self.assertEqual((result.published, result.failed), (1, 1))
        self.assertEqual(adapter.publish.call_count, 2)

    def test_database_failure_after_confirmation_leaves_event_retryable(self):
        adapter = InMemoryAdapter()
        with patch.object(OutboxEvent, "save", side_effect=DatabaseError("commit failed")):
            with self.assertRaises(DatabaseError):
                publish_pending(adapter=adapter)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.published_at)
        self.assertEqual(publish_pending(adapter=adapter).published, 1)
        self.assertEqual(adapter.messages[0], adapter.messages[1])

    def test_enqueue_requires_business_transaction(self):
        with self.assertRaises(RuntimeError):
            enqueue_event(self.event.event_type, self.rfq.pk, self.event.payload)

    def test_relay_rejects_call_inside_business_transaction(self):
        with transaction.atomic(), patch("procurement.events.publisher.get_broker_adapter") as factory:
            with self.assertRaises(RuntimeError):
                publish_pending()
        factory.assert_not_called()

    @override_settings(RABBITMQ_URL=None)
    def test_no_implicit_fake_adapter_when_rabbitmq_is_not_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            publish_pending()
        self.event.refresh_from_db()
        self.assertEqual(self.event.attempts, 0)

    def test_relay_command_with_explicit_test_adapter(self):
        output = StringIO()
        with patch("procurement.events.publisher.get_broker_adapter", return_value=InMemoryAdapter()):
            call_command("publish_procurement_outbox", limit=1, stdout=output)
        self.assertIn("Published: 1; failed: 0", output.getvalue())

    def test_relay_command_failure_and_invalid_limit(self):
        with patch("procurement.events.publisher.get_broker_adapter", return_value=InMemoryAdapter(confirmed=False)):
            with self.assertRaises(CommandError):
                call_command("publish_procurement_outbox", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("publish_procurement_outbox", limit=0, stdout=StringIO())

    def test_rabbitmq_adapter_enables_confirms_durability_and_mandatory_routing_without_network(self):
        pika = Mock()
        pika.BlockingConnection.return_value.channel.return_value.basic_publish.return_value = None
        adapter = RabbitMQAdapter(url="amqp://broker.example/vhost")
        with patch("procurement.events.adapters.importlib.import_module", return_value=pika):
            self.assertEqual(publish_pending(adapter=adapter).published, 1)
        channel = pika.BlockingConnection.return_value.channel.return_value
        channel.confirm_delivery.assert_called_once_with()
        channel.exchange_declare.assert_called_once_with(exchange="domain.events", exchange_type="topic", durable=True)
        self.assertTrue(channel.basic_publish.call_args.kwargs["mandatory"])
        properties = pika.BasicProperties.call_args.kwargs
        self.assertEqual(properties["delivery_mode"], 2)
        self.assertEqual(properties["message_id"], str(self.event.event_id))

    def test_rabbitmq_adapter_nack_or_unroutable_keeps_event_pending_without_network(self):
        pika = Mock()
        pika.BlockingConnection.return_value.channel.return_value.basic_publish.side_effect = RuntimeError("NACK or unroutable")
        with patch("procurement.events.adapters.importlib.import_module", return_value=pika):
            self.assertEqual(publish_pending(adapter=RabbitMQAdapter(url="amqp://broker.example/vhost")).failed, 1)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.published_at)
        self.assertEqual(self.event.attempts, 1)


class InboxConsumerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.request = request_factory()
        cls.item = create_request_item(cls.request)

    def alternative(self):
        return create_alternative_request(
            project_id=self.request.project_id, request_item=self.item,
            original_nomenclature_id=self.item.nomenclature_id, alternative_nomenclature_id=uuid4(),
        )

    def test_technical_review_updates_existing_domain_once(self):
        alternative = self.alternative()
        event = incoming("engineering.alternative_reviewed", {
            "alternative_request_id": str(alternative.pk), "technical_review_id": str(uuid4()), "decision": "approved",
        }, producer="engineering-service")
        self.assertTrue(dispatch_event(event))
        alternative.refresh_from_db()
        updated_at = alternative.updated_at
        self.assertEqual(alternative.status, AlternativeRequest.Status.TECHNICALLY_APPROVED)
        self.assertEqual(str(alternative.technical_review_id), event["payload"]["technical_review_id"])
        self.assertFalse(dispatch_event(event))
        alternative.refresh_from_db()
        self.assertEqual(alternative.updated_at, updated_at)
        self.assertIsNone(alternative.client_decision)
        inbox = InboxEvent.objects.get()
        self.assertEqual(inbox.status, InboxEvent.Status.PROCESSED)
        self.assertTrue(timezone.is_aware(inbox.processed_at))
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_technical_rejection_is_not_a_client_decision(self):
        alternative = self.alternative()
        dispatch_event(incoming("engineering.alternative_reviewed", {
            "alternative_request_id": str(alternative.pk), "technical_review_id": str(uuid4()), "decision": "rejected",
        }))
        alternative.refresh_from_db()
        self.assertEqual(alternative.status, AlternativeRequest.Status.TECHNICALLY_REJECTED)
        self.assertFalse(OutboxEvent.objects.filter(event_type="procurement.alternative_rejected").exists())

    def test_all_placeholder_subscriptions_are_noop_but_idempotently_processed(self):
        payloads = {
            "project.activated": {"project_id": str(uuid4())},
            "engineering.specification_approved": {"project_id": str(uuid4()), "specification_version_id": str(uuid4())},
            "engineering.specification_changed": {"project_id": str(uuid4()), "specification_version_id": str(uuid4())},
            "warehouse.shortage_detected": {"project_id": str(uuid4()), "nomenclature_id": str(uuid4()), "unit_id": str(uuid4()), "shortage_quantity": "2.000001"},
            "finance.expense_approved": {"project_id": str(uuid4()), "expense_id": str(uuid4()), "amount": "10.1234", "currency_code": "KZT"},
        }
        for name, payload in payloads.items():
            event = incoming(name, payload)
            self.assertTrue(dispatch_event(event))
            self.assertFalse(dispatch_event(event))
        self.assertEqual(InboxEvent.objects.filter(status=InboxEvent.Status.PROCESSED).count(), 5)
        self.assertEqual(PurchaseRequest.objects.count(), 1)
        self.assertFalse(RFQ.objects.exists())
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertEqual(set(CONSUMER_HANDLERS), set(CONSUMED_SCHEMAS))

    def test_repeat_event_does_not_repeat_business_effect_and_propagates_context(self):
        event = incoming(correlation_id=str(uuid4()), actor_id=str(uuid4()))
        handler = Mock(side_effect=lambda _: create_rfq(self.request))
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": handler}):
            self.assertTrue(dispatch_event(event))
            self.assertFalse(dispatch_event(event))
        handler.assert_called_once()
        self.assertEqual(RFQ.objects.count(), 1)
        outbox = OutboxEvent.objects.get()
        self.assertEqual(str(outbox.correlation_id), event["correlation_id"])
        self.assertEqual(str(outbox.causation_id), event["event_id"])
        self.assertEqual(str(outbox.actor_id), event["actor_id"])
        self.assertIsNone(get_event_context().correlation_id)

    def test_missing_correlation_uses_incoming_event_id(self):
        event = incoming()
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": lambda _: create_rfq(self.request)}):
            dispatch_event(event)
        self.assertEqual(str(OutboxEvent.objects.get().correlation_id), event["event_id"])

    def test_failed_handler_rolls_back_inbox_business_and_outbox_then_can_retry(self):
        event = incoming()

        def failing_handler(_):
            create_rfq(self.request)
            raise RuntimeError("failed handler")

        with patch.dict(CONSUMER_HANDLERS, {"project.activated": failing_handler}):
            with self.assertRaises(RuntimeError):
                dispatch_event(event)
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(RFQ.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertIsNone(get_event_context().correlation_id)
        with patch.dict(CONSUMER_HANDLERS, {"project.activated": lambda _: create_rfq(self.request)}):
            self.assertTrue(dispatch_event(event))
        self.assertEqual(RFQ.objects.count(), 1)

    def test_received_existing_inbox_row_is_processed(self):
        event = incoming()
        InboxEvent.objects.create(event_id=event["event_id"], producer=event["producer"], event_type=event["event_type"])
        self.assertTrue(dispatch_event(event))
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_outer_rollback_does_not_leave_processed_inbox(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                dispatch_event(incoming())
                raise RuntimeError("rollback")
        self.assertFalse(InboxEvent.objects.exists())

    def test_event_id_collision_with_other_producer_or_type_is_rejected(self):
        event = incoming()
        dispatch_event(event)
        for conflicting in (event | {"producer": "another-service"}, event | {
            "event_type": "engineering.specification_changed", "payload": {
                "project_id": str(uuid4()), "specification_version_id": str(uuid4()),
            },
        }):
            with self.assertRaises(ValueError):
                dispatch_event(conflicting)
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_invalid_envelopes_are_rejected_before_inbox_or_effect(self):
        valid = incoming()
        missing = valid.copy()
        del missing["event_id"]
        for event in (
            missing, valid | {"event_id": "bad"}, valid | {"event_version": 2},
            valid | {"occurred_at": "2026-10-04T10:00:00"}, valid | {"producer": ""},
            valid | {"correlation_id": "bad"}, valid | {"payload": {}},
            valid | {"event_type": "unsupported.event"},
        ):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    dispatch_event(event)
        self.assertFalse(InboxEvent.objects.exists())

    def test_legacy_consumer_import_uses_inbox_dispatcher(self):
        from procurement.infrastructure.events.consumers import dispatch_event as legacy_dispatch

        self.assertIs(legacy_dispatch, dispatch_event)
        event = incoming()
        self.assertTrue(legacy_dispatch(event))
        self.assertFalse(legacy_dispatch(event))


class HttpCorrelationTests(APITestCase):
    def payload(self):
        return {
            "project_id": str(uuid4()), "specification_version_id": str(uuid4()), "requested_by": str(uuid4()),
            "items": [{"nomenclature_id": str(uuid4()), "unit_id": str(uuid4()), "quantity": "1"}],
        }

    def test_http_correlation_id_is_preserved_in_outbox_and_response(self):
        correlation_id = uuid4()
        response = self.client.post(reverse("procurement:purchase-request-list"), self.payload(), format="json", HTTP_X_CORRELATION_ID=str(correlation_id))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response["X-Correlation-ID"], str(correlation_id))
        self.assertEqual(OutboxEvent.objects.get().correlation_id, correlation_id)
        self.assertIsNone(get_event_context().correlation_id)

    def test_missing_or_invalid_header_generates_uuid_without_breaking_api(self):
        identifiers = []
        for headers in ({}, {"HTTP_X_CORRELATION_ID": "invalid"}):
            response = self.client.post(reverse("procurement:purchase-request-list"), self.payload(), format="json", **headers)
            self.assertEqual(response.status_code, 201, response.data)
            identifier = UUID(response["X-Correlation-ID"])
            identifiers.append(identifier)
            event = OutboxEvent.objects.get(aggregate_id=response.json()["id"])
            self.assertEqual(event.correlation_id, identifier)
        self.assertNotEqual(*identifiers)

    def test_validation_failure_does_not_enqueue_or_leak_correlation(self):
        response = self.client.post(reverse("procurement:purchase-request-list"), {}, format="json", HTTP_X_CORRELATION_ID=str(uuid4()))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertIsNone(get_event_context().correlation_id)
        record = create_purchase_request(project_id=uuid4(), specification_version_id=uuid4(), requested_by=uuid4())
        self.assertIsNone(OutboxEvent.objects.get(aggregate_id=record.pk).correlation_id)
