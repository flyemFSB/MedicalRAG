---
status: accepted
---

# Aegra reuses the application-owned session

Aegra authenticates requests through a custom server-side authentication handler that validates the MedicalRAG Authentication Session in Redis. It does not issue or accept a second Aegra user token, OAuth identity, or independent Workspace membership record. The handler resolves the canonical User, Workspace memberships, and roles from the application-owned session and PostgreSQL-backed authorization model, then supplies a bounded runtime authorization context to the LangGraph execution.

## Consequences

- Aegra receives least-privilege access to the session namespace and must never log session identifiers, cookies, or raw medical content.
- Session revocation in MedicalRAG takes effect for new Aegra requests without waiting for a second token's expiry.
- Every assistant, Thread, Run, tool operation, retrieval call, and persisted runtime link must enforce the resolved Workspace scope; a client-supplied Workspace ID is only a routing hint.
- The authentication handler and Workspace authorization rules require contract tests shared with FastAPI so the two entry points cannot drift.
- Aegra's standard LangGraph adapter remains unchanged in the browser; the custom code is confined to the server-side authentication boundary.
