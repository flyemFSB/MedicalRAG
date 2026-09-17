---
status: accepted
related:
  - 0049-ragent-capability-complete-migration-matrix
  - 0053-docker-compose-yml-is-the-deployment-entrypoint
  - 0073-taskiq-replaces-arq-as-the-durable-job-queue
---

# RabbitMQ replaces Redis Streams as the TaskIQ transport

ADR 0073 adopted TaskIQ with the `RedisStreamBroker` (consumer groups + XAUTOCLAIM) as the durable job transport, and ADR 0049 rejected alternate message brokers **as replacement orchestration engines** (RocketMQ-style event topologies). This ADR amends the transport layer only: the TaskIQ transport swaps from Redis Streams to **RabbitMQ via `taskiq-aio-pika`**, without adding any new event topology, exchange fan-out, or cross-service messaging surface.

## Rationale

- **Real durability beats AOF-everysec.** Redis Streams trim at `maxlen=20_000` and lose up to ~1s of acknowledged writes on a crash (AOF `everysec`). RabbitMQ with persistent publishing (`DeliveryMode.PERSISTENT`) + a durable quorum task queue survives broker restarts with no trim bound — matching the ingestion pipeline's contract as the durable source of in-flight work (the PostgreSQL transactional outbox remains the write-side source of truth; RabbitMQ only carries work between relay and worker).
- **Poison-message handling follows the official playbook.** RabbitMQ's DLX documentation prescribes dead-lettering rejected/expired/over-limit deliveries instead of unbounded requeue loops; `taskiq-aio-pika` declares a dead-letter queue (`taskiq.dead_letter`) and wires `x-dead-letter-exchange` on every task queue by default, and quorum queues back it with at-least-once dead-lettering.
- **Fair dispatch comes built in.** Consumer prefetch (`qos=10`) implements the official consumer-side load control; under Redis Streams the worker had no in-flight bound.
- **Retry semantics are preserved, not re-invented.** `SmartRetryMiddleware` re-kicks failed tasks with a `delay` label; `AioPikaBroker` routes delay-labelled kicks through a TTL delay queue (`taskiq.delay`) that dead-letters back to the task queue. Task registration, middlewares (`SmartRetryMiddleware`, `IngestionFailureMiddleware`), the outbox relay, and all task code are unchanged — only the broker constructor and its URL move.
- **Ack semantics stay at-least-once.** TaskIQ's default `WHEN_SAVED` acknowledgment means a delivery is only confirmed after execution finishes; a worker crash mid-stage leaves the delivery unconfirmed and RabbitMQ redelivers it — the same crash-recovery story XAUTOCLAIM provided. Duplicate execution is absorbed by the existing `UNIQUE(run_id, stage)` idempotency (ADR 0073).

## Consequences

- New Compose service `rabbitmq` (`rabbitmq:4.3-management-alpine`, healthcheck `rabbitmq-diagnostics -q ping`, data volume); the worker `depends_on` it. Only the worker speaks AMQP — API and agent still touch PostgreSQL/Redis exclusively.
- `taskiq-redis` is removed from the worker's dependencies; `redis[hiredis]` stays (heartbeat key for the worker healthcheck).
- The task queue is a quorum queue on a single-node deployment: no replication benefit yet, but the type is the upgrade path to a clustered broker without re-declaring topology.
- The default 30-minute `consumer_timeout` applies to unacknowledged deliveries; no ingestion stage may block longer than that inside one task execution (the MinerU poller's bounded ~3-minute worst case is well inside it).
- Management UI is exposed on `127.0.0.1:15672` for operator debugging of queue depth and dead letters; credentials come from `RABBITMQ_USER`/`RABBITMQ_PASSWORD` env (see `.env.example`).

## References

- [RabbitMQ reliability guide](https://www.rabbitmq.com/docs/reliability)（persistent publish + durable queues + acks = at-least-once）
- [RabbitMQ dead letter exchanges](https://www.rabbitmq.com/docs/dlx)（rejected/expired/maxlen dead-lettering; prefer policy over hardcoded x-arguments）
- [RabbitMQ consumers guide](https://www.rabbitmq.com/docs/consumers)（prefetch / fair dispatch / consumer timeout）
- [taskiq-aio-pika](https://pypi.org/project/taskiq-aio-pika/)（0.6.0：`AioPikaBroker` qos、`delay_queue`、内置 `taskiq.dead_letter` 与持久化发布，verified against installed source 2026-09-12）
