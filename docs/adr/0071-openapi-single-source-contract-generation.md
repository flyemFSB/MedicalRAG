---
status: accepted
---

# OpenAPI is the single source of truth for `/api` contracts

MedicalRAG generates the Python↔TypeScript business-API contract from FastAPI rather than maintaining two hand-written DTO sets. FastAPI is the authoritative source: Pydantic models compile to the OpenAPI schema, and a codegen step (for example `openapi-typescript` or an equivalent) produces the TypeScript types consumed by the Vite SPA. A CI drift gate regenerates and diffs so a backend schema change cannot silently desynchronize the frontend.

`/api/agent` is exempt from generation. Its contract is Agent Protocol v2, a standardized protocol consumed through official adapters (`@assistant-ui/react-langgraph`, `@langchain/langgraph-sdk`); the application only pins the protocol version and event envelope rather than generating a second, parallel description of it.

## Why this shape

- The backend owns the business authority for `/api` (authentication, knowledge, ingestion, model targets, admin), so its OpenAPI output is an already-maintained, cost-free source of truth.
- Type-level generation plus contract tests covers drift without making the frontend validate `/api` responses at runtime.
- Generation produces types only; it does not generate client calls, because TanStack Query owns the request layer.

## Consequences

- Generated `/api` TypeScript types live under `apps/web` (`api/schema.json` → `src/api/schema.d.ts`). There is no installable `packages/contracts` package while web remains the only TypeScript consumer (deletion test / ADR 0060 amendment).
- Any change to FastAPI route/Pydantic models must regenerate and commit the TypeScript output; CI fails on an uncommitted diff (drift gate).
- The frontend trusts the generated types and the contract tests; it does not add a runtime validator over `/api` responses.
- Model, embedding, reranker, and MinerU provider protocols stay behind their own application-owned ports and are not part of the `/api` OpenAPI contract.
