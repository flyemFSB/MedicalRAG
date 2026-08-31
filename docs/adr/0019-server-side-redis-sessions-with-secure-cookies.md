---
status: accepted
---

# Browser authentication uses server-side Redis sessions

The browser authenticates with an opaque, high-entropy session identifier in a secure cookie. The corresponding Authentication Session is stored in Redis and contains only the minimum server-side state needed to identify the User, enforce expiry and revocation, and bind security controls; the browser does not store access JWTs or other bearer credentials in `localStorage` or session storage. Session identifiers are rotated after authentication and privilege changes, are invalidated on logout or security events, and are transmitted only over HTTPS with `HttpOnly`, `Secure`, and an explicit `SameSite` policy.

## Consequences

- Redis becomes part of the protected authentication request path and requires availability, namespace isolation, TTLs, monitoring, and a recovery policy.
- Session revocation is immediate and can be applied per device, per User, or per Workspace membership change.
- State-changing browser requests require an explicit CSRF defense; cross-origin API access must use a narrowly scoped CORS policy.
- Authentication and application data remain separate: Redis stores session state, while PostgreSQL remains the source of truth for Users, memberships, roles, and security events.
