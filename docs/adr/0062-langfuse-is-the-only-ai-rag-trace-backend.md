---
status: accepted
---

# Langfuse is the only AI/RAG Trace backend

MedicalRAG keeps one Trace capability: Aegra's official Langfuse integration for redacted AI/RAG observations. This preserves Ragent's inspectable run semantics without adding a custom Trace runtime or a second observability platform.

The integration may use OpenTelemetry internally because that is an Aegra implementation detail. MedicalRAG does not add OpenTelemetry SDKs, OTLP exporters, an OpenTelemetry Collector, Tempo, Grafana, manual spans, or a second LangChain/LangGraph Langfuse callback/exporter. Aegra is the only Langfuse ingestion owner for the hosted graph and LLM calls.

PostgreSQL remains the durable source of truth for `chat_runs`, `ingestion_runs`, `run_events`, and audit records. It may store an optional `langfuse_trace_id` for navigation, but it must not copy Langfuse observations or become a Trace backend. API and Worker infrastructure diagnostics use structured logs, metrics, health checks, and safe `request_id`/`run_id` correlation fields.

## Decision

- Configure Aegra's official Langfuse integration as the sole AI/RAG Trace path.
- Keep the Langfuse Python/server-compatible v4 line aligned with the selected Aegra release and verify the endpoint contract during implementation.
- Export only scrubbed operation metadata, model/provider versions, counts, timings, status, token usage where available, policy versions, and safe error classes by default.
- Never export raw prompts, medical questions, document/chunk/evidence text, patient identifiers, credentials, cookies, authorization headers, provider response bodies, or hidden chain-of-thought.
- Keep PostgreSQL business run/audit persistence independent of Langfuse. A missing trace must not invalidate a business run or workflow state.
- Make Langfuse export fail-open with bounded buffering, timeout, shutdown flush, and degraded structured logging/metrics.
- Use the Langfuse UI or API for AI/RAG observation detail; use PostgreSQL for product state and audit detail.

## Consequences

- Compose does not include Collector, Tempo, Grafana, Jaeger, or an observability-only storage service.
- API, Worker, and domain services do not create Langfuse clients or application-owned spans. They emit ordinary structured logs, metrics, and health signals.
- The system cannot provide distributed infrastructure Trace views across HTTP, SQL, Redis, Milvus, arq, and external providers. This is accepted for the current single-product scope; the correlation fields leave room for a future OTel addition.
- Langfuse is an operational dependency for AI/RAG inspection, so its data-egress, retention, access-control, masking, and availability policy must be reviewed separately, especially for medical content.
- Contract tests cover Aegra metadata, redaction, sampling, exporter failure, shutdown behavior, and `langfuse_trace_id` correlation. Business correctness tests do not require a live Langfuse endpoint.

## References

- [Aegra observability](https://docs.aegra.dev/guides/observability.md)
- [Langfuse Python SDK instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)
- [Langfuse native OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry.md)
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)
- [Langfuse self-hosted Docker Compose](https://langfuse.com/self-hosting/deployment/docker-compose.md)
