# Parcel Orders: Local Development

> Fictional training system. Commands and configuration describe an imagined Go
> repository; they are not runnable setup instructions for the Python
> Developer Documentation Agent.

## Local topology

The fictional `compose.yaml` runs PostgreSQL as service `postgres` and LocalStack
as service `localstack`. PostgreSQL exposes port `5432`, and LocalStack exposes
its AWS-compatible endpoint on port `4566`. The API, publisher, and worker run
on the host during development. LocalStack represents EventBridge and SQS for
this exercise; staging remains responsible for checking actual AWS behavior.

The repository's `make local-up` target runs `docker compose up -d`, waits for
dependency health checks, and executes `scripts/bootstrap-local.sh`. Bootstrap
creates the `parcel-orders` event bus, `route-order-created-v1` rule, worker
queue, both dead-letter queues, and the queue policy allowing the rule to send
messages. Repeating bootstrap reconciles resources without clearing messages.

## Configuration and startup

`config/local.yaml` contains nonsecret defaults:

```yaml
grpc_port: 50051
outbox_poll_interval: 2s
processing_deadline: 20s
consumer_name: order-preparer-v1
```

Environment variables override file settings. The fictional repository provides
these dummy local values in `.env.example`:

```sh
DATABASE_URL=postgres://parcel:local-only@localhost:5432/parcel?sslmode=disable
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
EVENT_BUS_NAME=parcel-orders
ORDER_QUEUE_URL=http://localhost:4566/000000000000/parcel-order-preparation
```

The application explicitly reads `AWS_ENDPOINT_URL` when configuring its AWS
clients. `ORDER_QUEUE_URL` must match the URL returned by local bootstrap; the
example assumes the local endpoint URL strategy. These dummy credentials are
for the emulator only. The local setup script exports the environment before
starting Go processes; the application does not automatically read `.env` files.

After infrastructure startup, `make migrate-up` applies the versioned database
migrations. Run `go run ./cmd/api`, `go run ./cmd/publisher`, and
`go run ./cmd/worker` in separate terminals with the same environment. The API
accepts gRPC traffic on `localhost:50051`. A checked-in `examples/create-order.json`
contains a stable `client_request_id` for testing duplicate requests.

## Health and readiness

Each process exposes `/healthz` and `/readyz` over HTTP: API on `8081`, publisher
on `8082`, and worker on `8083`. Health reports whether the process is running.
Readiness additionally checks dependencies needed for that process's work.

The API requires database connectivity and the expected migration version. It
does not require EventBridge because it commits notifications to the outbox.
The publisher requires PostgreSQL and access to `parcel-orders`. The worker
requires PostgreSQL and access to `ORDER_QUEUE_URL`. Readiness failures return
HTTP `503`; logs identify the failing dependency without printing credentials.

## Common problems and inspection

If a process moves into Docker Compose, `localhost` refers to that container.
Use `postgres:5432` and `http://localstack:4566` from the Compose network, and
obtain a queue URL reachable from that container. A host-only queue URL can
break a worker even when its separate AWS endpoint setting is correct.

If orders remain `PENDING`, inspect unpublished outbox rows first, then routing,
queue depth, and worker logs. An increasing outbox backlog suggests publication
trouble; queued messages suggest consumption trouble. Check
`parcel-routing-dlq` for exhausted EventBridge delivery failures and
`parcel-order-preparation-dlq` for repeated worker failures.

To exercise redelivery, the fictional worker supports
`WORKER_EXIT_AFTER_COMMIT_ONCE=true`: it exits after one committed transaction,
before deleting the message. Restart without that flag and wait for the
60-second visibility period to expire. The receipt described in `database.md`
should prevent duplicate work. `docker compose down` stops local dependencies;
removing volumes is a separate, intentional data reset.
