---
kind: ticket
label: wayfinder:research
status: accepted
parent: ../map.md
assignee: codex
title: Official Langfuse observability research
research_file: ../../research/langfuse-observability.md
---

## Question

Can Langfuse provide the AI/RAG Trace required by MedicalRAG without duplicating Aegra's Agent Protocol/runtime state or exporting medical content?

## Accepted answer

Yes. Configure the current Langfuse Python/server-compatible v4 line through Aegra's official integration and make Aegra the only Langfuse ingestion owner. Do not add an independent LangChain/LangGraph callback, second exporter, OpenTelemetry Collector, Tempo, Grafana, or custom runtime. API and Worker diagnostics use structured logs, metrics, and health checks; PostgreSQL stores business run/audit records and an optional `langfuse_trace_id`.

The Langfuse export is fail-open and must not receive prompts, document/chunk text, patient identifiers, credentials, cookies, authorization headers, or model output by default. Aegra may use OpenTelemetry internally to implement its official exporter, but no application-wide OTel contract is introduced. Langfuse Cloud is the recommended first deployment target when scrubbed metadata egress is approved; official self-hosted Compose remains optional and does not provide HA, scaling, or backup by itself.
