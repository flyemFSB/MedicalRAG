---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - ragent-capability-migration-matrix.md
  - milvus-hybrid-retrieval-contract.md
  - ingestion-and-mineru-state-machine.md
  - external-provider-and-egress-contracts.md
  - identity-workspace-and-safety-boundary.md
  - frontend-contracts-and-assistant-ui.md
  - compose-topology-and-operations.md
  - official-python-backend-and-data-stack-research.md
  - official-agent-and-frontend-stack-research.md
  - official-retrieval-ingestion-and-storage-research.md
  - official-devops-quality-security-and-observability-research.md
title: Testing, parity evidence, and release gates
---

## Question

What unit, contract, integration, end-to-end, retrieval-evaluation, security, accessibility, migration, observability, and failure-injection coverage is required before declaring Ragent behavioral parity and implementation readiness?

## Resolution

- **Test pyramid** — unit (medical-core rules/state machines/policies with in-memory adapters, no external services); contract (FastAPI OpenAPI/error structure, event envelope, Agent Protocol v2 against Aegra, provider adapters); integration (Compose `test` profile: PostgreSQL, Redis, Milvus, MinIO, the arq worker + outbox relay, Langfuse fail-open); end-to-end (Playwright on the Vite SPA: login, chat stream, sources, feedback, admin flows). See the specification's Testing Decisions and the monorepo research §5.3/§7.
- **Retrieval evaluation** — `eval-retrieval` runs on every PR (Recall@k, MRR/nDCG, intent Top-1, branch correctness, empty-recall rate, duplicate rate, P95 latency) on a synthetic or approved de-identified set; `eval-answer` (RAGAS LLM metrics) runs on nightly/release candidates; the clinical-safety review stays expert-driven and never reduces to a RAGAS score.
- **Security** — OWASP-aligned checks at the trust boundary: authentication, ownership, request validation, upload limits, and egress/redaction (no prompts, patient identifiers, or credentials in logs/Trace).
- **Accessibility** — automated scans (axe-core/Playwright) combined with manual review for the chat and operator surfaces.
- **Migration** — Alembic can create the schema from an empty database; index rebuild and Active Index Version cutover are tested.
- **Observability** — business run/audit persistence independent of Langfuse; Langfuse observation redaction, sampling, and fail-open exporter behavior.
- **Failure injection** — provider outage → routing failover → deterministic evidence-insufficiency; arq retry exhaustion → terminal failure + operator replay; Redis/PostgreSQL unavailable → degraded readiness; outbox relay crash → re-scan/re-deliver with consumer idempotency.
- **Parity evidence** — every row of the migration matrix ([stack](../../reference/stack-replacement-matrix.md) + [behavior](../../reference/behavior-parity-matrix.md)) carries a status and a test seam; parity fixtures assert Ragent-observable behavior (event order, short-circuit semantics, failure codes). A capability is parity-complete only when its row has a passing fixture ([ADR 0049](../../adr/0049-ragent-capability-complete-migration-matrix.md)).
- **Release gates** — per-commit: format/lint/typecheck/unit; Pull Request: + contract tests + `eval-retrieval` + affected web build; merge/release: Compose `test`-profile integration, migration test, Playwright E2E, `eval-answer`, image build; release checklist pins the lockfiles and re-runs the upgrade-group contract tests.
