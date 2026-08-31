---
status: accepted
---

# Aegra runs as an independent Compose runtime

Aegra is deployed as an independent LangGraph Server and Worker runtime in the Docker Compose topology. The same-origin gateway exposes the Aegra LangGraph endpoint under `/api/agent`, while FastAPI remains the authority for application authentication, Workspace membership, business APIs, medical knowledge, ingestion control, and safety policy. Aegra owns Agent Thread and Run execution, checkpointing, leases, recovery, and Agent Protocol streaming; it is not embedded into the FastAPI request process and is not replaced by a local fallback in production.

## Consequences

- The Compose deployment must define private network paths, health checks, startup ordering, worker capacity, graceful shutdown, and separate server/worker structured logs and metrics for Aegra. Aegra's graph/LLM observations use its official Langfuse integration; no additional system tracing stack is required.
- Aegra and FastAPI share PostgreSQL and Redis infrastructure only through explicit databases, schemas, key namespaces, and credentials; ownership remains split according to ADR-0002.
- The gateway must not expose Aegra's administrative endpoints or internal service port directly to browsers.
- Aegra's LangGraph endpoint requires a server-side authentication and Workspace-scope handoff compatible with the application-owned Redis session.
- The medical retrieval and application-service boundary must be packaged so the Aegra runtime can execute it without moving business ownership into the frontend or duplicating rules in a second implementation.
