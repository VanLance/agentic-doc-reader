# Parcel Orders: Events

> Fictional training system. Event names and operational settings form a small
> documentation corpus, not deployed AWS infrastructure.

## Version 1 contract

The publisher submits `OrderCreated.v1` to EventBridge bus `parcel-orders` with
source `parcel.orders`. The application envelope below is the event's `detail`;
EventBridge adds its own outer envelope when delivering to SQS.

```json
{
  "event_id": "11111111-1111-4111-8111-111111111111",
  "event_version": 1,
  "occurred_at": "2026-09-19T14:00:00Z",
  "order_id": "22222222-2222-4222-8222-222222222222",
  "customer_id": "customer-demo-42"
}
```

`event_id` is the outbox row's identifier and stays unchanged across publication
retries. It is distinct from EventBridge's outer event ID and the SQS message
ID. The worker uses the application `event_id` for deduplication. The event
announces a committed order; current order data remains in PostgreSQL.

The worker requires all five fields, validates UUID identifiers and timestamp
syntax, and accepts only integer `event_version=1`. Additive fields are ignored.
A breaking change requires a new detail type and version, with an explicit
consumer rollout rather than silently changing version 1 semantics.

## Publication and routing ownership

The API writes the order and outbox together. The publisher polls every two
seconds and marks `published_at` only after the individual EventBridge entry is
accepted. It checks per-entry failures even when the overall request succeeds.
Unaccepted rows remain unpublished for later attempts. Acceptance means the bus
received the event, not that the worker processed it.

Rule `route-order-created-v1` matches source `parcel.orders` and detail type
`OrderCreated.v1`, targeting standard queue `parcel-order-preparation`. The
queue policy permits that rule to send messages. No input transformer is used:
the worker parses the SQS body as an EventBridge envelope and then reads
`detail`.

EventBridge owns retries when delivery to the queue fails. This fictional target
is configured with a maximum event age of 3,600 seconds and 10 retry attempts.
Eligible exhausted deliveries go to `parcel-routing-dlq`. That queue is separate
from failures that occur after the worker receives a message.

## Consumption, timeout, and deletion

The Go worker long-polls for up to 20 seconds and processes one message at a
time per worker instance. Queue visibility timeout is 60 seconds. Each message
has a 20-second processing deadline, leaving time for transaction cleanup and
deletion. This training worker does not extend visibility; longer workloads
would require revisiting that choice.

After receipt, the message is temporarily hidden from other consumers. The
worker validates its envelope, commits the receipt and order update described
in `database.md`, then calls `DeleteMessage` using the current receipt handle.
Deletion is the acknowledgement. If processing fails, it does not delete the
message; after visibility expires, another receive can retry it.

Standard queues can deliver duplicates and do not guarantee ordering. Even a
successful transaction may be followed by a crash before deletion. The
`processed_events` key `(consumer_name, event_id)` makes that redelivery safe
for consumer `order-preparer-v1`.

## Dead letters and recovery

The worker queue uses `maxReceiveCount=5` and DLQ
`parcel-order-preparation-dlq`. Repeated unsuccessful receives eventually move a
message there; this is a receive-count policy, not a five-second timer or an
exact schedule. Invalid envelopes follow the same failure path and produce
structured error logs.

An operator inspects dead letters, fixes the cause, and redrives worker failures
to the source queue while preserving application event IDs. Routing failures
require separate inspection and replay to the intended destination. Neither
DLQ automatically repairs orders: affected orders can remain `PENDING` until
processing succeeds. Never assign a fresh event ID merely to bypass a receipt.
