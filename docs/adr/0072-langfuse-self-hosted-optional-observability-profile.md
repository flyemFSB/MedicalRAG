---
status: accepted
updated_by: ADR-0082
---

# Langfuse is self-hosted as an optional observability profile

> **2026-08 修正（ADR 0082）**：`observability` profile 后端切换为 Phoenix（Postgres 后端，见 [ADR 0082](0082-phoenix-replaces-langfuse-as-observability-backend.md)）；Langfuse 自托管栈退役，本文的 profile-optional、data-sovereignty 与 fail-open 原则继续有效。

> **2026-08 修正（ADR 0076）**：医疗内容脱敏**不以 `mask_otel_spans` 为机制**——Aegra 0.9.24 的 OTLP 导出无此钩子（见 [ADR 0076](0076-aegra-owns-langfuse-ingestion-via-otlp.md)）；脱敏靠 Aegra 默认脱敏观测字段 + 应用侧数据出境策略。Langfuse 自托管仍为可选 `observability` profile；若启用，Aegra OTLP 出口指向自托管端点。

MedicalRAG self-hosts Langfuse for v1 in an optional `observability` Compose profile instead of using Langfuse Cloud. This follows the product's data-sovereignty posture: medical AI/RAG trace data stays on the operator's own infrastructure. Langfuse's MIT core is free to self-host; Cloud remains a later option, not a v1 dependency. Aegra's OTLP export targets the self-hosted Langfuse OTLP ingest endpoint ([ADR 0062](0062-langfuse-is-the-only-ai-rag-trace-backend.md)).

Self-hosting adds a real footprint — Langfuse requires PostgreSQL (shared with the product), ClickHouse, Redis/Valkey, and S3-compatible storage (the existing MinIO) — which is exactly why the profile is optional and Langfuse export is fail-open: an unavailable Langfuse only degrades observability and never blocks a chat answer, ingestion transition, arq job acknowledgement, or business-state persistence.

## Consequences

- The `observability` Compose profile, when enabled, provisions ClickHouse plus Langfuse web/worker and points Aegra's OTLP export at Langfuse; the base `docker-compose.yml` does not require it.
- Trace retention is bounded (configurable days) and sampling is enabled; medical content is redacted at export via `mask_otel_spans`; cross-border policy is satisfied by keeping data on the self-hosted instance.
- Langfuse access is operator-only; the operator opens Langfuse for AI/RAG detail and reads PostgreSQL for business run/audit detail.
- Cloud adoption later is a configuration change, not a migration; the SDK and Trace-ownership decision is already accepted and unchanged.
