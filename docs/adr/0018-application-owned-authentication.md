---
status: accepted
---

# Authentication is owned by the application

MedicalRAG uses an application-owned authentication system. User accounts, password credentials, login sessions, account recovery, credential rotation, and Workspace authorization are managed by MedicalRAG; the first version does not depend on OIDC, OAuth login, Auth0, Keycloak, or another external identity provider. External providers remain limited to explicitly approved document extraction, embedding, and generation workloads and must not become the system of record for User identity or Workspace membership.

## Consequences

- Passwords must be stored only as memory-hard password hashes, never plaintext or reversible encryption.
- Authentication endpoints must implement rate limiting, generic failure messages, session invalidation, recovery-token expiry, and security-event auditing.
- Workspace membership and roles are evaluated by the backend on every protected resource boundary.
- The browser authentication transport, CSRF policy, refresh/session rotation, and cookie settings are separate decisions to be finalized before implementation.
