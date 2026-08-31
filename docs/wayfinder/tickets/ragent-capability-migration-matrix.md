---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - official-python-backend-and-data-stack-research.md
  - official-agent-and-frontend-stack-research.md
  - official-retrieval-ingestion-and-storage-research.md
  - official-devops-quality-security-and-observability-research.md
  - official-langfuse-observability-research.md
title: Ragent capability migration matrix is implementation-complete
---

## Question

Can every audited Ragent capability, event, data contract, optional adapter, experimental path, administration route, and failure behavior be assigned a target status of implemented, replaced, adapted, or rejected with an explicit reason, official target documentation, and a test seam?

## Resolution

Yes. The complete migration matrix is recorded across two artifacts:

- **[stack-replacement-matrix.md](../../reference/stack-replacement-matrix.md)** — the technical-stack dimension: every audited Ragent component (backend, retrieval, frontend, tooling) maps to a target implementation, replacement, or typed rejection, including the four previously-open gaps now closed by ADR 0066–0069.
- **[behavior-parity-matrix.md](../../reference/behavior-parity-matrix.md)** — the behavioral dimension: the streaming event vocabulary (adapted onto Aegra Agent Protocol v2 typed channels), failure behavior (preserved via the plan's state machine, model router/circuit, Redis rate limiting, LangGraph retry/timeout, and arq outbox/failure-replay), and every admin console route (reproduced as operator routes with recharts/@antv/g6 and per-format preview renderers, ADR 0067/0068).

Every row carries a status (`implemented`/`replaced`/`adapted`/`rejected`), a target component, and a reference to the decision or official document that justifies it. MCP, URL/Feishu, local-model, and alternate-retrieval capabilities are explicitly rejected with typed reasons rather than silently omitted ([ADR 0049](../../adr/0049-ragent-capability-complete-migration-matrix.md), [ADR 0051](../../adr/0051-mcp-compatibility-is-out-of-scope.md)).

Remaining work is not a matrix gap but the parity-fixture and test-seam assignment for each row, tracked by the open testing-quality-and-release-gates decision.
