---
kind: ticket
label: wayfinder:research
status: accepted
parent: ../map.md
assignee: codex
research_file: ../../research/trace-architecture-and-backends.md
title: Official production tracing architecture and backend research (historical)
---

## Question

What are the mainstream production-grade tracing options for MedicalRAG, and is a separate distributed tracing backend necessary for the current scope?

## Accepted answer

The research compared OpenTelemetry, Collector, Tempo, Grafana, and Jaeger as mainstream distributed tracing options. They are technically valid, but they are not required by the current MedicalRAG scope and are deliberately excluded from the implementation target. Aegra's official Langfuse integration is sufficient for redacted AI/RAG observations.

The accepted target uses one Langfuse path for graph/LLM observations, structured logs/metrics/health checks for API and Worker diagnostics, and PostgreSQL for durable `chat_runs`, `ingestion_runs`, `run_events`, and audit records. PostgreSQL may store an optional `langfuse_trace_id`/safe correlation id but does not store the observation tree. The application does not add OpenTelemetry SDKs, a Collector, Tempo, Grafana, Jaeger, or a custom Trace runtime.

This decision accepts the loss of distributed infrastructure Trace views across HTTP, SQL, Redis, Milvus, arq, and external providers. `request_id` and `run_id` remain in safe logs and business records so a future OTel addition does not require a domain-model rewrite. See [ADR 0062](../../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md) for the implementation decision.
