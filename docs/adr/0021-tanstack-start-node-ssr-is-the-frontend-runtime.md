---
status: superseded
---

# TanStack Start runs as a Node SSR frontend

> Superseded by [ADR 0070](0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md). MedicalRAG now runs a Vite SPA with a same-origin Nginx/Vite proxy; TanStack Start Node SSR is removed. This document records the original SSR decision for history.

The production frontend runs TanStack Start as a Node server with server-side rendering and hydration. TanStack Start owns presentation concerns—React rendering, route composition, loader orchestration, document metadata, and frontend error boundaries—but does not become a second business backend. FastAPI remains the sole authority for authentication, Workspace authorization, medical retrieval, ingestion, model-provider calls, and persisted business state. Frontend server loaders and browser requests use the same versioned `/api` contract rather than duplicating domain logic in Node.

## Consequences

- The deployment includes a separately health-checked Node frontend container and a FastAPI container behind the same gateway.
- SSR code must forward the authenticated request context safely when it calls internal FastAPI endpoints and must not log session cookies or medical content.
- Chat streaming remains an `/api` SSE concern; the frontend renders the stream and does not call model or MinerU providers directly.
- Build, runtime, and browser-compatible environment variables must be explicitly separated; provider secrets never enter the client bundle.
