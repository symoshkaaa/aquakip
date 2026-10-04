# Aqua Kip Procurement Demo

The React/Vite UI uses the existing Django/DRF API. No sample responses are substituted in the application.

## Run

From the repository root:

```sh
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_procurement_demo
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

In another terminal, from `frontend/`:

```sh
npm install
npm run dev
```

Use the URL printed by Vite. Development requests go through Vite's proxy to Django, not port 5500. `VITE_API_URL` in `.env` accepts an absolute URL (default `http://127.0.0.1:8000/api/v1`) or `/api/v1/`. A relative URL uses Django port 8000 as the development proxy target. Production deployments should use a same-origin reverse proxy, or configure CORS for an absolute API origin.

## Workflow

1. Create a supplier, or open one of the seeded suppliers.
2. Create a purchase request with multiple items. External project, specification, user, nomenclature and unit identifiers remain UUID inputs because their services are not part of this demo.
3. Open the request and create an RFQ. Add suppliers as recipients.
4. Create offers against the RFQ and its actual request items.
5. Create a comparison, select a real offer, and save its item snapshot with criteria. JSON results are rendered recursively without inventing scores. Selection is manual, not an automated scoring engine.
6. Create an order from the comparison or offer. Supplier, project, currency and items are prefilled; the backend calculates the total using Decimal.
7. Approve a draft order, then send an approved order. The UI displays the status returned by the backend and hides completed actions.

The sidebar also includes alternatives and expected deliveries. Tracking JSON is expandable; an early delivery displays its recorded justification. Dashboard counts aggregate all pages of the real list APIs.

## Seed

`seed_procurement_demo` creates 3 suppliers, 2 requests with 4 items, 2 RFQs, 6 recipients, 3 offers with 6 items, a comparison, 3 orders (draft/approved/sent), 2 deliveries and an alternative. Re-running it preserves existing demo records and their current statuses; it does not erase or reset user data. Dates are relative to the first run.

## Verification

```sh
# From the repository root
.venv/bin/python manage.py test

# From frontend/
npm run build
npx playwright install chromium
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

With Django and Vite running, in another terminal from `frontend/`:

```sh
npm run test:e2e
```

The default browser-test URL is `http://127.0.0.1:5174`. Override it with `DEMO_BASE_URL`. Tests cover desktop/mobile navigation, details, safe error states, search and the full creation/approval/sending workflow. The latter writes clearly labelled `E2E-*` records into the connected database: use a disposable local database, never production. Only error-handling tests inject synthetic HTTP 500/409 responses. Screenshots and traces are under `test-results/`.

## Scope

This is a working domain demo, not production integration with IAM, Reference Data, Documents, Engineering or Integration Hub. Send records the backend transition/event; actual delivery to a supplier depends on the external integration. Comparison scoring, persisted source-offer linkage on orders, edit/cancel workflows, alternative decisions and delivery registration forms are outside this frontend stage.

## Integration Events

Business operations now persist Outbox events in the same database transaction. The demo does not require RabbitMQ and does not automatically publish pending events. Send still represents the domain transition, not confirmation that a supplier received a document. Consumer subscriptions use a transactional Inbox for deduplication.

Event contracts, TODO handlers, correlation IDs, optional RabbitMQ setup and the separate relay command are documented in the [project README](../README.md).
