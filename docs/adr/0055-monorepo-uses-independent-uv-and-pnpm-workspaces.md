---
status: accepted
---

# The repository uses independent uv and pnpm workspaces

MedicalRAG is one monorepo containing independently deployable FastAPI, Aegra, Worker, and evaluation Python applications plus a Vite SPA web application. Python projects are coordinated by one uv workspace and JavaScript projects by one pnpm workspace; the two ecosystems keep separate manifests and lockfiles. `apps/api`, `apps/agent`, and `apps/worker` depend on `packages/medical-core` and the shared `packages/infra` adapter package, while `packages/contracts` contains cross-runtime wire schemas and generated frontend types. Applications never import one another, and each application owns its composition root.

## Consequences

- The repository has one root `uv.lock` and one root `pnpm-lock.yaml`; each package still declares its own direct dependencies.
- `medical-core` is a deep domain/application kernel, not a miscellaneous utility package. It owns Ragent-parity medical rules and ports; FastAPI and Aegra own delivery/runtime bindings.
- `packages/infra` is the renamed shared adapter package. It is not nested under `apps/api`, because Agent and Worker need overlapping database, queue, provider, storage, and observability adapters.
- `packages/contracts` is not a second domain model. It is the versioned HTTP/event schema boundary used to generate TypeScript types and validate contract drift.
- Turborepo is used for the JavaScript/TypeScript task graph; uv remains the Python dependency and command runner.
- `packages/ui`, `packages/testkit`, `packages/config`, `packages/common`, and `packages/utils` are intentionally absent. Their would-be responsibilities remain local to the consuming app/member or an explicitly owned domain/adapter module.
- The root `docker-compose.yml` remains the deployment boundary, while `infra/` stores service-specific configuration and initialization assets.
