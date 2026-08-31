---
status: accepted
---

# Aegra owns the only Langfuse integration

MedicalRAG uses Langfuse as the sole AI/RAG Trace backend. Aegra's official integration records scrubbed observations for its hosted Agent graph and LLM calls. The current official Python SDK/server-compatible line is v4 (research snapshot `4.14.1`), and the integration is configured in Aegra's runtime rather than in `packages/infra`.

Langfuse is not the business database or Agent Protocol runtime state source of truth. PostgreSQL remains the source of truth for durable business run records, workflow events, and audit events shown in the operator UI; those records may carry an optional `langfuse_trace_id` but do not copy the observation tree. FastAPI, Worker, and domain services do not initialize a Langfuse client or create a second application tracing pipeline. Aegra remains the source of truth for Thread/Run execution, checkpoints, recovery, leases, and Agent Protocol stream state. Aegra is the sole Langfuse ingestion owner for its graph/LLM observations, and no second callback or exporter is added to its graph/LLM invocation. Aegra may use OpenTelemetry internally to implement the official integration; that is not a MedicalRAG platform dependency.

## Consequences

- The default fields exported from Aegra to Langfuse are service name, environment, code/provider/model versions, operation name, duration, status, retry count, token counts, candidate counts, policy versions, safe error classes, and correlation IDs that are approved for external observability.
- Raw prompts, complete model responses, document/chunk text, patient identifiers, credentials, cookies, authorization headers, provider response bodies, and hidden chain-of-thought are excluded by default. Retrieval observations contain counts and policy metadata rather than medical content.
- Aegra sends one scrubbed graph/LLM observation stream to Langfuse through its official integration. MedicalRAG does not enable Aegra's Generic OTLP target for a second backend, add a Collector/Tempo/Grafana stack, or create application-owned spans. Agent Protocol v2 remains a thread/command/SSE transport contract, while Langfuse is the AI/RAG observability backend.
- Langfuse native OTLP is configured over HTTP/JSON or HTTP/protobuf, not gRPC; the v4 ingestion header is required by the selected Langfuse endpoint. The exact endpoint, SDK, server, and OpenTelemetry versions are locked together and covered by a contract test.
- Aegra's Langfuse export is bounded and fail-open. Langfuse authentication errors, timeouts, queue saturation, exporter shutdown, or endpoint outages mark Aegra observability degraded and never fail an Agent run. API and Worker business run/audit persistence is independent of Langfuse availability; redaction runs before the exporter receives its copy.
- Langfuse Cloud is the recommended first deployment target when the data-egress policy permits scrubbed metadata. A self-hosted Langfuse deployment is an optional Compose profile; the official Compose topology is suitable for local/VM use but does not itself provide HA, horizontal scaling, or backups. Self-hosting therefore requires a separate data-retention, access-control, backup, and upgrade review.
- Aegra integration tests include observation metadata contracts, redaction, queue bounds, exporter failure, sampling, and shutdown flush behavior. Structured-log and metrics tests cover safe `request_id`/`run_id` correlation; PostgreSQL tests separately cover business run/audit persistence. Tests do not assert vendor-internal tracing implementation details or require Langfuse to be available for business correctness.

## References

- [Langfuse Python SDK instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation.md)
- [Langfuse LangChain integration](https://langfuse.com/integrations/frameworks/langchain.md)
- [Langfuse native OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry.md)
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking.md)
- [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose.md)
- [Langfuse self-hosting versioning](https://langfuse.com/self-hosting/upgrade/versioning.md)
- [Langfuse latest Python package metadata](https://pypi.org/pypi/langfuse/json)
- [Aegra observability](https://docs.aegra.dev/guides/observability.md)
- [OpenTelemetry Python documentation](https://opentelemetry.io/docs/languages/python/)
