---
status: accepted
---

# FastAPI and Aegra share a narrowed `medical-core` domain seam

`packages/medical-core` is the shared domain seam between FastAPI, Aegra, and the Worker. It holds the entities, value objects, state machines, policies, ports, and deterministic domain services for conversations, intent resolution, slot normalization, retrieval, Evidence Fusion, safety, and ingestion that the three processes must agree on. FastAPI delivery handlers, Aegra LangGraph nodes, and arq worker jobs compose that package through the same application services and domain interfaces; neither process reimplements medical rules or routes domain behavior through a chain of internal HTTP calls.

The chat-pipeline orchestration is deliberately **not** in `medical-core`: the LangGraph `StateGraph` assembly, node bindings, checkpoint/retry/timeout configuration, and the Aegra runtime hookup live in `apps/agent`, so `medical-core` stays free of LangGraph and Aegra dependencies and remains testable with a plain pytest without any graph runtime. `medical-core` must remain independent of FastAPI request objects, LangGraph SDK details, UI message formats, and provider-specific response types.

Concrete PostgreSQL, Redis, Milvus, arq, object-storage, external-provider, structured logging, metrics, and health implementations live in the separate shared `packages/infra` adapter package. Aegra owns its official Langfuse integration. Each process owns its dependency-injection container and configuration.

## Consequences

- `packages/medical-core` must remain independent of FastAPI request objects, LangGraph SDK details, UI message formats, and provider-specific response types.
- LangGraph and Aegra dependencies are confined to `apps/agent`; the `StateGraph` assembly and checkpoint/retry/timeout configuration are graph-runtime concerns, so they never enter `medical-core`, `infra`, or the API/Worker composition roots.
- `packages/infra` may depend on `medical-core` ports and models, but must not be nested under `apps/api` or make the domain package depend on infrastructure SDKs.
- Aegra Graph nodes are thin orchestration bindings over `medical-core` domain services; domain invariants and medical safety decisions remain testable without starting Aegra or FastAPI.
- FastAPI and Aegra may scale independently but must run compatible package and migration versions.
- No mutable in-process cache or singleton may be treated as cross-process state; shared state belongs in PostgreSQL, Redis, Milvus, or object storage according to ownership.
