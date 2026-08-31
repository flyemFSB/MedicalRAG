---
status: superseded
---

# OpenTelemetry and Tempo are the system tracing standard

> Superseded by [ADR 0062](0062-langfuse-is-the-only-ai-rag-trace-backend.md). This document records the rejected application-wide OpenTelemetry/Collector/Tempo/Grafana design for decision history; it is not the implementation target.

MedicalRAG uses OpenTelemetry as the only distributed-tracing API, context-propagation contract, and application instrumentation boundary. The OpenTelemetry Collector is the production gateway. Grafana Tempo is the canonical technical trace backend and Grafana is the operator query surface.

PostgreSQL does not store technical spans. It stores durable business run records, workflow events, and audit events. Those records contain their own `run_id` and may contain an `otel_trace_id` for correlation. A missing or expired sampled trace does not invalidate a business record.

Aegra remains the owner of graph and LLM instrumentation. Aegra fans out scrubbed semantic observations to Langfuse and generic OTLP observations to the Collector. Langfuse is an LLM/agent analysis sink, not the system trace source of truth. FastAPI, Agent, Worker, external provider adapters, and messaging adapters send only to the Collector and do not initialize Langfuse.

## Decision

- Use OpenTelemetry SDKs, official/contrib instrumentation where stable, and explicit manual spans for Milvus, MinerU, reranker, embedding, generation, and RocketMQ boundaries without a stable instrumentation package.
- Use one internal OTLP Collector gateway with bounded memory, batching, retry, sampling, and redaction processors.
- Use Tempo with S3-compatible object storage. MinIO is the Compose development and controlled single-site storage implementation; production HA requires replicated or managed object storage.
- Use Grafana for trace search, trace-to-metrics correlation, dashboards, and operator access control.
- Keep PostgreSQL `chat_runs`, `ingestion_runs`, and `run_events` for durable product state and audit, not span storage.
- Configure Aegra's generic OTLP target to the Collector and its Langfuse target only for scrubbed Aegra graph/LLM semantic observations. Do not add a second Langfuse callback or exporter to the same graph.

## Why not the alternatives

- Jaeger v2 is an approved mainstream alternative and remains a local fallback. Its production documentation requires a persistent backend; its scalable primary backends add OpenSearch/Elasticsearch/Cassandra, while Badger is single-instance and limited to modest volumes. That is a worse fit for the current no-Elasticsearch boundary and existing MinIO deployment.
- Jaeger all-in-one with in-memory storage is a development profile only because restarts lose traces.
- Langfuse alone cannot replace distributed tracing across HTTP, SQL, Redis, Milvus, and RocketMQ, and its medical data egress controls make it inappropriate as the universal sink.
- PostgreSQL custom trace tables preserve business auditability but do not provide standard propagation, span querying, sampling, retention, or cross-service visualization.

## Consequences

- The Compose topology adds Collector, Tempo, and Grafana services plus a Tempo object-storage configuration. It does not add Elasticsearch solely for observability.
- `packages/infra/observability` contains OTel setup and ordinary structured-log/metrics correlation. The PostgreSQL repository is a business `RunEventRepository`/audit adapter and must not be used for technical spans.
- Trace export is fail-open. API, Agent, and Worker correctness cannot depend on Collector, Tempo, Grafana, or Langfuse availability.
- Trace retention and access control become explicit operational settings. Medical content is redacted before any exporter and is not recovered from trace storage.
- Production scaling and disaster recovery are separate from Compose. Collector and Tempo can scale out, but MinIO must be replicated or replaced by a supported object-storage service before claiming HA.

## References

- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/index.md)
- [Collector deployment patterns](https://opentelemetry.io/docs/collector/deployment/)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/index.md)
- [Jaeger architecture](https://www.jaegertracing.io/docs/latest/architecture/)
- [Jaeger storage backends](https://www.jaegertracing.io/docs/latest/storage/)
- [Grafana Tempo setup](https://grafana.com/docs/tempo/latest/setup/)
- [Grafana Tempo configuration](https://grafana.com/docs/tempo/latest/configuration/)
- [Aegra observability](https://docs.aegra.dev/guides/observability.md)
- [Langfuse native OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry.md)
