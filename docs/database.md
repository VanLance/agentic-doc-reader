# Parcel Orders: Database

> Fictional training system. Schema and SQL illustrate the imagined Go service;
> this database is not a dependency of the Developer Documentation Agent.

## Schema ownership and migrations

PostgreSQL is the authority for order state. Versioned SQL migrations live in
`db/migrations`; `make migrate-up` applies them before application startup.
Migration `001_initial.sql` creates `orders`, `outbox_events`, and
`processed_events`. Applied migrations are immutable: later changes use a new
migration. The API readiness check rejects an unexpected schema version.

The `orders` table uses UUID `order_id` as its primary key. It stores non-null
`customer_id`, `client_request_id`, `request_hash`, `line_items`, `status`, and
`created_at`, plus nullable `ready_at`. A unique constraint named
`orders_customer_request_key` covers `(customer_id, client_request_id)`.
`line_items` is JSONB; the API validates one to twenty items, each with a SKU and
positive integer quantity. Database checks require a JSON array with one to
twenty entries, while detailed item validation remains an API responsibility.

A status check allows only `PENDING` and `READY`. Another check requires
`ready_at` to be null for `PENDING` and non-null for `READY`. The only supported
transition is `PENDING -> READY`, enforced by the worker's conditional update.
A status constraint alone does not enforce transition direction.

## Creating an order atomically

The API starts a transaction and attempts to insert the order:

```sql
INSERT INTO orders
  (order_id, customer_id, client_request_id, request_hash, line_items, status)
VALUES ($1, $2, $3, $4, $5, 'PENDING')
ON CONFLICT (customer_id, client_request_id) DO NOTHING
RETURNING order_id;
```

`created_at` defaults to the database's current timestamp. If insertion returns
an identifier, the API adds an `outbox_events` row in the same transaction.
That row has UUID primary key `event_id`, foreign key `order_id`, JSONB
`payload`, `created_at`, and nullable `published_at`. The payload contains the
version 1 application envelope documented in `events.md`.

If insertion returns no row, a subsequent query at `READ COMMITTED` reads the
existing order and compares `request_hash`. The hash uses a canonical form of
the validated request. Matching content returns the existing order; different
content returns gRPC `ALREADY_EXISTS`. The duplicate path creates no outbox row.

## Idempotent worker transaction

The receipt table contains non-null `consumer_name`, UUID `event_id`, and
`processed_at`, with primary key `(consumer_name, event_id)`. Worker processing
starts by attempting this insertion within a transaction:

```sql
INSERT INTO processed_events (consumer_name, event_id, processed_at)
VALUES ('order-preparer-v1', $1, now())
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;
```

No returned row means the receipt already exists; the worker can finish the
transaction without another state change. A new receipt requires the worker to
update the referenced order where `status = 'PENDING'`, setting status to
`READY` and `ready_at = now()`. If exactly one order is not updated, processing
fails and the entire transaction rolls back, including the new receipt.

Concurrent deliveries of the same event compete on the receipt's unique key.
PostgreSQL resolves that conflict, so two workers cannot both commit processing
for the same consumer and event. Receipts are retained indefinitely in this
small training system; deleting them would weaken replay protection.

## Data access and delivery boundaries

Named queries live in `db/queries` and generate Go methods through sqlc. The
worker uses transaction-bound queries for both receipt insertion and order
update, and deletes the SQS message only after commit. A crash before deletion
therefore causes a safe duplicate delivery. This guarantee covers these
database writes; external side effects would need their own strategy.
