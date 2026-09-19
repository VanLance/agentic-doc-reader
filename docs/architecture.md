# Parcel Orders: Architecture

> Fictional training system. This document is sample knowledge for the Developer
> Documentation Agent, not infrastructure implemented by that Python project.

## Purpose and service boundaries

Parcel Orders accepts orders and prepares them for fulfillment asynchronously.
The Go API owns request validation and order creation. A background worker owns
preparation. PostgreSQL holds authoritative order state. EventBridge routes
notifications, and SQS buffers work so temporary worker outages do not require
clients to keep requests open.

The service has three Go entry points: `cmd/api`, `cmd/publisher`, and
`cmd/worker`. Protobuf definitions live in `proto/orders/v1`; generated gRPC code
lives in `internal/gen`. Business rules live in `internal/orders`, while
`internal/store` contains sqlc-generated access to PostgreSQL. Transport handlers
call business operations rather than embedding SQL or queue logic directly.

## Synchronous API contract

The gRPC method `orders.v1.OrderService/CreateOrder` accepts `customer_id`,
`client_request_id`, and one to twenty line items. Each item has a SKU and a
positive quantity. The server listens on port `50051` and assigns a UUID
`order_id`. A successful response means the order was stored with status
`PENDING`; it does not mean background preparation has finished.

The API creates the order and an outbox record in one PostgreSQL transaction.
The outbox contains the notification that must eventually be published. A unique
constraint on `(customer_id, client_request_id)` prevents repeated requests from
creating multiple orders. Reusing that pair with the same payload returns the
existing order; a different payload returns `ALREADY_EXISTS`.

## Asynchronous publication and routing

The publisher polls unpublished outbox rows every two seconds. It submits each
notification to the EventBridge bus `parcel-orders`, using source
`parcel.orders` and detail type `OrderCreated.v1`. The event detail contains a
stable `event_id`, an `event_version` of `1`, and the order identifier.

The publisher marks an outbox row published only after its individual entry is
accepted. If publication succeeds but recording that success fails, it may send
the notification again. Retries preserve the same application `event_id`.

The EventBridge rule `route-order-created-v1` matches that source and detail
type and targets the standard SQS queue `parcel-order-preparation`. The worker
reads the application envelope from the EventBridge message's `detail` field.
Routing does not update order state.

## Worker processing and failure boundaries

The worker long-polls SQS and prepares each order inside a database transaction.
It inserts a receipt into `processed_events` and changes the order from
`PENDING` to `READY`. The receipt's primary key is `(consumer_name, event_id)`,
with consumer name `order-preparer-v1`. Duplicate receipt insertion uses
`ON CONFLICT DO NOTHING`; an existing receipt means this consumer already
committed the work. These database rules are expanded in `database.md`.

The worker deletes the SQS message only after the transaction commits. A crash
after commit but before deletion causes redelivery without another state change.
A failed transaction rolls back both receipt and state update, leaving a retry
able to perform the work. `PENDING -> READY` is the only supported transition;
temporary processing failures leave the order `PENDING`.

## Operational expectations

The queue visibility timeout is 60 seconds, and the worker's per-message
processing deadline is 20 seconds. Its redrive policy uses `maxReceiveCount=5`
and dead-letter queue `parcel-order-preparation-dlq`. A separate EventBridge
target-delivery DLQ, `parcel-routing-dlq`, captures exhausted routing failures.
See `events.md` for retry ownership and recovery procedures.

The complete path is client → gRPC API → PostgreSQL order/outbox → publisher →
EventBridge → SQS → Go worker → PostgreSQL. The outbox closes the gap between
saving an order and scheduling its notification; it does not eliminate duplicate
delivery. Local PostgreSQL and LocalStack setup is described in
`local-development.md`.
