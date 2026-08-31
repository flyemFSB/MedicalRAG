---
status: accepted
updated_by: ADR-0082
related:
  - 0059-langfuse-is-a-fail-open-operational-observability-sink
  - 0062-langfuse-is-the-only-ai-rag-trace-backend
  - 0072-langfuse-self-hosted-optional-observability-profile
---

# Aegra owns the Langfuse ingestion via environment-driven OTLP

> **2026-08 修正（ADR 0082）**：摄取后端由 Langfuse OTLP 端点切换为 Phoenix（`OTEL_TARGETS=PHOENIX` + `PHOENIX_COLLECTOR_ENDPOINT`，见 [ADR 0082](0082-phoenix-replaces-langfuse-as-observability-backend.md)）。「Aegra 唯一摄取 owner / fail-open / 应用不自建 exporter 与 span tree」原则不变；`LANGFUSE_*` 配置面退役，`langfuse.*` 语义属性由通用语义属性（`user.id`/`session.id`）承接。

MedicalRAG records its only AI/RAG Trace through Aegra's official Langfuse integration. Aegra builds an `OTLPSpanExporter` from environment configuration and ingests observations into Langfuse's OTLP endpoint (`{BASE}/api/public/otel/v1/traces`) with the required `x-langfuse-ingestion-version: 4` header and Basic auth. The application does not initialize a Langfuse client, add a second callback/exporter, or construct span trees (ADR 0059/0062).

## Rationale

- **Single ingestion owner**: Aegra's integration is the only exporter; API, Worker, and domain services emit only structured logs, metrics, and health data (ADR 0062).
- **Version-baseline alignment**: version-baseline §3 pins Langfuse 4.14.x; OTLP over HTTP with the version header is the only supported ingestion path.

## Consequences

- **Configuration surface**: Aegra reads `OTEL_TARGETS=LANGFUSE`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_SAMPLE_RATE` from the environment. These are deployment configuration, not application settings.
- **No `mask_otel_spans` hook in Aegra 0.9.24**: the `mask_otel_spans` masking hook exists only in the Langfuse Python SDK's self-managed exporter. Aegra 0.9.24's OTLP exporter does not expose it; using it would require a second exporter, which ADR 0059 forbids. Medical-content redaction therefore relies on Aegra's default scrubbed observation fields and the application's Data Egress Policy at the provider boundary. This corrects ADR 0072's wording (which named `mask_otel_spans` as the masking mechanism).
- **Fail-open**: an unavailable Langfuse endpoint only marks AI/RAG observability degraded; it never blocks a chat answer, ingestion transition, message acknowledgement, or business persistence (ADR 0059).
- **Contract tests** may exercise Aegra's OTLP export path with an injected in-memory exporter in the integration profile; the application side asserts only that no Langfuse client is initialized outside Aegra.

## References

- [Aegra observability docs](https://docs.aegra.dev/observability) and [aegra/aegra](https://github.com/aegra/aegra) `database.py`/OTLP exporter source (verified 2026-08-04).
- Langfuse self-hosting and native OTLP documentation (`/api/public/otel`, `x-langfuse-ingestion-version: 4`).
