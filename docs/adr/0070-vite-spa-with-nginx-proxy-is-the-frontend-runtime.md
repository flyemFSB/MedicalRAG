---
status: accepted
supersedes:
  - 0021-tanstack-start-node-ssr-is-the-frontend-runtime.md
---

# Vite SPA with a same-origin Nginx/Vite proxy is the frontend runtime

The MedicalRAG frontend is a Vite single-page application served statically; TanStack Start Node SSR is dropped. A login-required medical workbench has no SEO or initial-render requirement that justifies an SSR server, so removing it reduces the web tier to static assets plus a same-origin proxy. React, Vite 8, TypeScript 6, and assistant-ui remain unchanged.

- **Development**: the Vite dev server proxies `/api` (and `/api/agent`) to FastAPI/Aegra through `server.proxy`.
- **Production**: Nginx serves the SPA build and reverse-proxies `/api` → FastAPI and `/api/agent` → Aegra, so chat SSE reaches the backend directly without a Node hop.

The same-origin entrypoint ([ADR 0020](0020-same-origin-entrypoint-for-web-and-api.md)) and the assistant-ui Agent Protocol v2 integration ([ADR 0058](0058-assistant-ui-uses-native-agent-protocol-v2-runtime.md)) are unchanged: the browser keeps the same HttpOnly session cookie and talks to `/api` and `/api/agent` through the same origin.

## Why not SSR

- A login-gated internal workbench has no public-crawlable or first-paint-critical content; SSR buys nothing the user can observe.
- Removing the Node SSR container and its server-loaders/context-forwarding code eliminates a whole process, a build target, and a class of session-propagation bugs for no product value.

## Consequences

- The `apps/web` service is a static build (no Node SSR container); production adds an Nginx container (or host reverse proxy) that serves the SPA and proxies `/api` + `/api/agent`.
- No server loaders, no SSR hydration, no Node-side internal-API forwarding; provider secrets never enter the client bundle.
- TanStack Start is no longer a frontend dependency; browser requests go straight to the same-origin `/api` and `/api/agent` endpoints.
- Vite `server.proxy` (dev) and the Nginx location blocks (prod) must preserve `Upgrade`/SSE headers for the streaming endpoints.
