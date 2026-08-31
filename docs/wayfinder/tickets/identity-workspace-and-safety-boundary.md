---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - ragent-capability-migration-matrix.md
  - official-python-backend-and-data-stack-research.md
  - official-devops-quality-security-and-observability-research.md
title: Identity, Workspace, and Safety Boundary
---

## Question

What exact User, Authentication Session, Workspace, Workspace Member, role, operator, ownership, audit, medical safety class, and data-egress rules must be enforced at FastAPI, Aegra, Milvus, the arq worker, logs, and external-provider boundaries?

## Resolution

- **Identity** — application-owned User with Argon2id password hashing ([ADR 0018](../../adr/0018-application-owned-authentication.md)); an Authentication Session is a server-side Redis session in an HttpOnly Secure cookie ([ADR 0019](../../adr/0019-server-side-redis-sessions-with-secure-cookies.md)); Aegra reuses the application session ([ADR 0024](../../adr/0024-aegra-reuses-the-application-session.md)) — there is no separate Aegra identity.
- **Workspace** — the isolation scope ([ADR 0003](../../adr/0003-workspace-is-the-resource-isolation-scope.md)); Workspace Member membership plus role governs access to its resources. System Knowledge is read-only for all Workspaces ([ADR 0004](../../adr/0004-system-knowledge-is-read-only-and-workspace-knowledge-is-private.md)); Workspace Knowledge is private to its Workspace.
- **Roles and operator** — member roles within a Workspace plus a separate operator role for admin routes, both authorized at FastAPI. Every user-owned record carries `owner_id`/`workspace_id`; no cross-workspace read path exists.
- **Enforcement at boundaries** — FastAPI enforces authentication, ownership, and validation; Aegra reuses the session and maps Conversations↔threads; Milvus enforces authorization through scalar filters (`workspace_id`/`knowledge_base_id` plus `is_eligible`); the arq worker inherits ownership from the aggregate id and never bypasses Workspace scope; logs and Trace never contain prompts, document text, patient identifiers, or credentials ([ADR 0062](../../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md)); external providers receive only de-identified, policy-permitted content ([ADR 0008](../../adr/0008-first-version-excludes-identifiable-patient-data.md) and the Data Egress Policy).
- **Medical safety** — intent nodes carry a safety class; prohibited individual requests short-circuit before retrieval ([ADR 0043](../../adr/0043-prohibited-individual-requests-short-circuit-before-retrieval.md)); every answer carries the fixed disclaimer ([ADR 0042](../../adr/0042-fixed-medical-ai-disclaimer.md)); answers remain evidence-first without clinical decisions.
- **Audit** — business run records and audit events carry actor/Workspace scope, policy versions, counts, and failure codes (the run/audit adapter in `packages/infra`); the operator reads these for audit detail.
