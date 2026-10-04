# Aqua Kip Procurement

Existing Django/DRF domain services and React/Vite demo. Frontend setup and the demo workflow are documented in [frontend/README.md](frontend/README.md).

## Event Architecture

```text
HTTP / domain service
  -> transaction.atomic: business records + OutboxEvent
  -> database commit

separate outbox relay
  -> lock pending OutboxEvent
  -> serialize immutable envelope
  -> broker adapter + publisher confirmation
  -> published_at (only on confirmation)

incoming envelope
  -> validate schema/version
  -> transaction.atomic: InboxEvent + domain handler
  -> processed_at/status + database commit
  -> transport ACK
```

Implementation lives in `procurement/events/`: schemas, envelope serialization, context/middleware, publisher, adapters, Inbox handlers, transport, topology, logging and readiness. Existing `procurement/infrastructure/events/` queue/dispatcher import paths forward to this layer; inline logging publication and `on_commit` broker callbacks are removed. Business services never contact RabbitMQ.

### Envelope

All events carry `event_id`, `event_type`, `event_version`, `occurred_at`, `correlation_id`, `causation_id`, `company_id`, `project_id`, `actor_id`, `producer`, and `payload`. Outgoing producer is `procurement-service`; current schema version is `1`. UUIDs and Decimal amounts are serialized as strings; timestamps are timezone-aware ISO 8601. Nullable metadata is included as JSON null, not omitted.

`aggregate_type` and UUID `aggregate_id` are stored in Outbox, with the actual record identifier also present in the typed payload. Company/project/actor metadata is persisted separately from payload so retries serialize exactly the same envelope. Request creation uses the actual `requested_by` as actor; other operations leave actor null unless an event context supplies it. Purchase orders have no company field, so a supplier's company is not guessed as the order's company.

`X-Correlation-ID` is accepted as a UUID and echoed in the response. Missing or invalid headers generate a UUID without changing API behavior. ContextVar scope is reset on success and failure. Incoming handlers retain correlation (or fall back to the incoming event ID) and use the incoming event ID as causation for any resulting Outbox events. Direct service calls outside HTTP may have null correlation metadata.

## Published Event Contracts

These schemas are registered and enqueued by the existing services. Values come from model records and their TextChoices, not invented fields.

| Event | Service | Payload |
| --- | --- | --- |
| `procurement.request_created` | `create_purchase_request` | `purchase_request_id`, `project_id`, `specification_version_id` |
| `procurement.rfq_created` | `create_rfq` | `rfq_id`, `purchase_request_id`, `status` |
| `procurement.rfq_sent` | `mark_rfq_sent` | `rfq_id`, `purchase_request_id`, `status`, `updated_at` |
| `procurement.supplier_offer_received` | `register_supplier_offer` | `supplier_offer_id`, `rfq_id`, `supplier_id`, `status` |
| `procurement.supplier_offer_verified` | `verify_supplier_offer` | `supplier_offer_id`, `rfq_id`, `supplier_id`, `status` |
| `procurement.comparison_created` | `create_supplier_comparison` | `comparison_id`, `purchase_request_id`, `version` |
| `procurement.alternative_requested` | `create_alternative_request` | `alternative_request_id`, `project_id`, `request_item_id`, `original_nomenclature_id`, `alternative_nomenclature_id` |
| `procurement.alternative_approved` | `record_alternative_client_decision` | `alternative_request_id`, `project_id`, `client_decision`, `status` |
| `procurement.alternative_rejected` | `record_alternative_client_decision` | Same fields as alternative approval |
| `procurement.purchase_order_created` | `create_purchase_order` | `purchase_order_id`, `project_id`, `supplier_id`, `number`, `currency_code`, `total_amount` |
| `procurement.purchase_order_approved` | `approve_purchase_order` | `purchase_order_id`, `status`, `approved_at` |
| `procurement.purchase_order_sent` | `mark_purchase_order_sent` | `purchase_order_id`, `status`, `sent_at` |
| `procurement.delivery_expected` | `record_expected_delivery` | `expected_delivery_id`, `purchase_order_id`, `planned_date`, `status` |
| `procurement.delivery_delayed` | `record_expected_delivery` when status is delayed | Same fields as expected delivery |

RFQ has no `sent_at`: its existing draft-to-open transition uses the persisted `updated_at`. Order transition payloads use real `approved_at`/`sent_at`, not a synthetic `changed_at`. Technical rejection of an alternative is distinct from a client decision and does not emit the client-decision event.

There is no existing delivery-update service, so delayed events are emitted when recording a delivery with `ExpectedDelivery.Status.DELAYED`; no new update action or automatic date-based status change is invented. Direct ORM writes bypass domain services and intentionally do not emit integration events. Historical/demo records are not backfilled into Outbox.

## Subscriptions

The incoming contracts preserve the payload fields from the existing subscription skeleton. No new external domain behavior is inferred.

| Event | Required Payload | Handler Effect |
| --- | --- | --- |
| `project.activated` | `project_id` | TODO, acknowledged no-op |
| `engineering.specification_approved` | `project_id`, `specification_version_id` | TODO, acknowledged no-op |
| `engineering.specification_changed` | `project_id`, `specification_version_id` | TODO, acknowledged no-op |
| `warehouse.shortage_detected` | `project_id`, `nomenclature_id`, `unit_id`, `shortage_quantity` | TODO, acknowledged no-op |
| `engineering.alternative_reviewed` | `alternative_request_id`, `technical_review_id`, `decision` | Calls existing `record_alternative_technical_review`; decision is approved/rejected |
| `finance.expense_approved` | `project_id`, `expense_id`, `amount`, `currency_code` | TODO, acknowledged no-op |

Call `procurement.events.consumers.dispatch_event(envelope)`, not a handler directly. It returns True for a newly processed event and False for a previously processed event. Both outcomes are successful deliveries. Unknown event types, unsupported versions, malformed envelopes and handler errors raise; the transport must not ACK them as processed.

## Outbox / Inbox Guarantees

- The business write and Outbox insert share the service's `transaction.atomic`. Either both commit or both roll back. `enqueue_event` rejects calls outside a transaction.
- `publish_pending` runs separately and rejects invocation from inside a business transaction. Each pending row is locked during a short relay transaction containing broker I/O and the publication marker. This is not the business transaction.
- PostgreSQL uses `SELECT FOR UPDATE SKIP LOCKED` to separate concurrent relay workers. SQLite does not implement row locking: run only one relay/consumer worker with the local demo database.
- The adapter must return exactly True after confirmation. Exceptions, NACKs, unroutable messages and missing confirmations leave `published_at` null. `attempts` counts completed publication attempts, including successful ones. A failed row is attempted at most once per batch; a later invocation retries it.
- Broker confirmation followed by a database/process failure can cause redelivery. This is **at-least-once**, not exactly-once broker delivery; event ID and serialized envelope remain unchanged across retries.
- Inbox uses a globally unique `event_id` primary key, insert-race protection and a row lock. Handler effects, resulting Outbox events, `processed_at` and status commit together. Duplicate deliveries skip the handler. Reuse of an ID with another producer/type is rejected.
- A failed handler rolls back Inbox and all its database effects, allowing retry. External network effects must not run inside handlers; use Outbox for follow-on integrations. ACK only after the outermost database transaction commits, including for deduplicated messages.
- No-op TODO subscriptions are intentionally marked processed. They do not create requests, alter specifications or approve expenses. Later business policies require an explicit replay/backfill plan for previously acknowledged events.
- Ordering across retries or parallel workers is not guaranteed. Use one relay where ordering matters until aggregate sequence/order policies are specified.

## RabbitMQ Setup

The optional real `RabbitMQAdapter` lazily imports Pika and connects only in the relay. The consumer/setup/readiness commands connect only when explicitly invoked. The Django API, seed and unit tests do not require Pika or a broker. `InMemoryAdapter` is available only through explicit injection for tests; an unconfigured relay never silently substitutes it or marks events delivered. Supplying `RABBITMQ_URL` enables the broker part of readiness, not an automatic background worker or a startup connection.

Install optional broker dependencies:

```sh
.venv/bin/python -m pip install -r requirements-rabbitmq.txt
```

Inject these environment variables through the deployment's secret/config manager:

```text
RABBITMQ_URL=<AMQP or AMQPS URL from your secret manager>
RABBITMQ_EXCHANGE_DOMAIN=domain.events
RABBITMQ_EXCHANGE_DEAD=dead.letter
RABBITMQ_PROCUREMENT_QUEUE=procurement.events
```

Do not commit credentials. Provision a broker/vhost and then run the idempotent topology setup. It requires a modern RabbitMQ with quorum queues (the integration stack uses 4.1). Application users need configure/read/write permissions on the configured exchanges/queues. Incompatible pre-existing queue arguments produce an error, not destructive recreation.

```sh
.venv/bin/python manage.py setup_procurement_rabbitmq
.venv/bin/python manage.py consume_procurement_events
.venv/bin/python manage.py check_procurement_readiness
```

The consumer declares topology again on reconnect, uses manual ACK and prefetch 1 per queue, closes stale Django connections, and handles SIGINT/SIGTERM gracefully. Broker outages use interruptible reconnect backoff (1 to 30 seconds). `--max-messages N` optionally bounds consumed deliveries, including failed/quarantined ones. A connection/ACK/NACK failure closes the channel: unacknowledged deliveries remain owned by RabbitMQ, not marked successful by the process.

Readiness returns JSON and a nonzero command exit code when a configured dependency is unreachable. It checks `SELECT 1` and an AMQP connection/channel; it is not a replacement for queue-backlog, subscription-consumer, or broker-cluster health monitoring. With no `RABBITMQ_URL`, it checks only the database. No Django startup hook contacts the broker.

### Topology and Retry Policy

| Resource | Configuration |
| --- | --- |
| `domain.events` | Durable topic exchange; six inbound keys listed above bind to `procurement.events` |
| `dead.letter` | Durable topic exchange; `procurement.events.dead` binds the DLQ |
| `procurement.events` | Initial processing queue, attempt 1 |
| `procurement.events.attempt-2/3/4` | Processing queues for the three later attempts |
| `procurement.events.retry.1m/5m/30m` | Separate TTL queues: 60000 / 300000 / 1800000 ms |
| `procurement.events.dlq` | Final queue, no TTL and no automatic replay |
| `procurement.events.retry` | Durable direct exchange routing failures to the appropriate delay |
| `procurement.events.retry.return` | Durable direct exchange returning each delay to its next attempt queue |

All eight queues are durable quorum queues. Processing and retry queues use at-least-once dead-lettering with `reject-publish` overflow. TTLs and routing are explicit queue arguments: changing them on existing queues requires a planned topology migration. RabbitMQ retains dead letters until destination confirmation under this [quorum dead-lettering configuration](https://www.rabbitmq.com/docs/quorum-queues#dead-lettering); ordinary DLX forwarding is not sufficient for this safety property.

```text
attempt 1 --NACK--> retry 1m --TTL--> attempt 2
attempt 2 --NACK--> retry 5m --TTL--> attempt 3
attempt 3 --NACK--> retry 30m --TTL--> attempt 4
attempt 4 --NACK--> DLQ
```

Every application failure uses `basic_nack(requeue=False)`, never an immediate requeue loop. A message gets at most four normal handler attempts. Each stage also has a quorum delivery limit of 5 for repeated connection/process crashes; exhausting that limit advances through the same finite pipeline. A permanently unavailable dead-letter destination leaves a retained pending message, not an infinite business-handler retry. TTL is a minimum delay, not a strict scheduling guarantee under outages/backlog. See [RabbitMQ TTL](https://www.rabbitmq.com/docs/ttl) and [dead-letter routing](https://www.rabbitmq.com/docs/dlx).

Malformed envelopes, unknown types and incompatible versions are **delayed quarantine**: validation rejects them at every stage, no business handler executes, no ACK is sent, and after the same three delays they reach DLQ (nominally 36 minutes). This deliberately keeps the strict no-ACK-on-error contract without application republishing or a publish/ACK ownership gap. Logs distinguish `invalid_envelope`, `unsupported_event_type` and `unsupported_event_version`. Original body/event ID remain unchanged; broker `x-death` headers preserve the rejection/expiration history. Attempt comes from the processing queue, not an untrusted event header.

The two private direct exchanges keep retries inside Procurement. They do not fan out the event again to other domain subscribers. The transport wraps the existing Inbox dispatcher in an outermost durable database transaction. Validation, handler effects and Inbox processing must succeed and commit before ACK, including duplicate deliveries; commit errors receive NACK. A lost ACK after commit may redeliver, but Inbox deduplication prevents a repeated handler effect.

### Publisher and Logs

The adapter declares `domain.events` durable, uses event type as routing key, sends persistent JSON messages, enables publisher confirms, and publishes with `mandatory=True`. An exchange without matching queue bindings is not treated as successful delivery. Procurement setup binds only inbound events: receiving services must provision bindings for outgoing `procurement.*` events. There is no catch-all queue that disguises missing downstream subscriptions. Connection setup and broker blocking have bounded timeouts.

[Pika delivery-confirmation API](https://pika.readthedocs.io/en/stable/examples/blocking_delivery_confirmations.html) and [BlockingConnection API](https://pika.readthedocs.io/en/stable/modules/adapters/blocking.html) describe the broker-confirmation behavior used by the adapter.

Run one bounded batch from a scheduler or supervised worker:

```sh
.venv/bin/python manage.py publish_procurement_outbox --limit 100
```

Failed batches exit nonzero and leave unconfirmed rows pending. The relay skips published rows, locks each batch row, and attempts a failed row only once per invocation. Schedule bounded batches with deployment retry cadence/backoff; publisher outages leave events in Outbox rather than dropping business events into consumer DLQ. SQLite permits only one relay; PostgreSQL supports concurrent workers with `SKIP LOCKED`.

`procurement.events` logs are JSON with event ID/type, correlation, causation, producer, attempt, result and error. Only exception class/static validation codes are logged, not exception messages, event payloads, connection URLs or credentials. Invalid metadata is sanitized. Pika's own connection diagnostics are suppressed because they can include URLs. Publisher success logs follow the relay database commit, not just broker confirmation.

## Local Integration

Keep the fast SQLite path unchanged. Install optional PostgreSQL/RabbitMQ dependencies and run the real integration suites in an isolated temporary Compose project:

```sh
.venv/bin/python -m pip install -r requirements-integration.txt
.venv/bin/python scripts/run_integration.py --docker
```

The runner generates ephemeral credentials in process environment, chooses free localhost ports unless explicitly supplied, starts PostgreSQL 16 plus RabbitMQ 4.1 management, runs all backend tests plus PostgreSQL-specific tests, then real broker tests. It removes only its own uniquely named containers/volumes in `finally`. No credentials are written to disk. Existing demo SQLite data, queues and containers are not purged. Integration queues/exchanges use random isolated namespaces. Retry tests inject 100/200/300 ms TTLs for speed; production setup is also tested twice with the real 1m/5m/30m arguments. The destination-outage test can take about three minutes because it waits for the broker's own [internal dead-letter forwarding retry](https://www.rabbitmq.com/blog/2022/03/29/at-least-once-dead-lettering), independent of application retry TTLs.

For a persistent local stack, supply values through environment or an ignored `.env.integration` based on `.env.integration.example`. Required secrets are `POSTGRES_PASSWORD` and `RABBITMQ_PASSWORD`; set `RABBITMQ_URL` to the matching URL, with URL-encoded credentials. Defaults: database `procurement_db`, user `procurement`, PostgreSQL port 5433, AMQP 5673, management 15673; all bindings are localhost-only. Set alternate ports when occupied. These are local integration services, not a conversion of the app to Docker.

```sh
docker compose --env-file .env.integration -f docker-compose.integration.yml up -d --wait
# Export the matching environment into this shell before these commands:
.venv/bin/python manage.py migrate --settings=procurement_service.settings_integration
.venv/bin/python manage.py test integration_tests.postgres_suite --settings=procurement_service.settings_integration
.venv/bin/python manage.py test integration_tests.rabbitmq_suite --settings=procurement_service.settings_integration
# Or run both suites and backend regressions against existing services:
.venv/bin/python scripts/run_integration.py
docker compose --env-file .env.integration -f docker-compose.integration.yml down
```

Integration modules deliberately use `*_suite.py`, not `test_*.py`, so normal `manage.py test` never attempts a broker or PostgreSQL connection. Django creates a separate test database; the integration database user needs database-creation permission. PostgreSQL checks cover unique IDs, rollbacks, real row locks, concurrent Inbox insert races, concurrent relay `SKIP LOCKED`, exact Decimal precision, JSONB and all declared Procurement indexes/constraints. Broker checks cover A-F, actual engineering alternative handling, manual ACK verified across channel closure, unsupported/malformed events, mandatory-routing failure, runner shutdown, idempotent setup, readiness and dead-letter destination outages.

## Operational Follow-Up

Production deployment still needs TLS/least-privilege credentials, multi-node quorum/HA and broker-restart/load/partition drills, supervised workers and publisher scheduling, backlog/oldest-event/DLQ alerts, approved manual replay procedures and Inbox/Outbox retention. DLQ must not be automatically replayed into an unlimited loop. Replay valid failed events with the same event ID after fixing the cause; schema conversion/version upgrades require an explicit migration policy. The five existing no-op domain subscriptions still need product policies and a deliberate backfill plan; this transport stage does not invent those effects.

## Verification

```sh
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```

The event tests cover all 14 produced schemas/services, atomic rollback, broker-confirmation boundaries, retry envelope stability, publisher failure counters, Inbox deduplication, consumer rollback/retry, HTTP correlation and a mocked real RabbitMQ adapter without network access. The original domain/API tests remain intact. Frontend APIs and routes are unchanged.
