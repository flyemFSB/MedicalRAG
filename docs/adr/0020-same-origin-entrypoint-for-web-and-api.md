---
status: accepted
---

# Web and API use one HTTPS origin

The production web application is exposed through one HTTPS origin. A reverse proxy routes browser page and asset requests to the Vite SPA frontend and routes `/api` requests to FastAPI; internal service names and ports are never exposed to the browser. This same-origin boundary is deliberate because it keeps authentication cookies first-party, minimizes CORS, and gives the platform one place to apply TLS, request-size limits, security headers, request IDs, access logs, and upstream health checks.

## Consequences

- The gateway must support streaming responses and Server-Sent Events without buffering or premature idle timeouts.
- FastAPI remains the authority for authentication, authorization, business APIs, and medical safety controls; the gateway is not an authorization layer.
- The frontend and backend may still be deployed as separate containers and scaled independently.
- Local development should preserve the same `/api` path shape so browser behavior matches production.
