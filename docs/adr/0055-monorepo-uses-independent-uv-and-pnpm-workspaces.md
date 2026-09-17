---
status: accepted
---

# The repository uses independent uv and pnpm workspaces

MedicalRAG is one monorepo containing independently deployable FastAPI, Aegra, Worker, and evaluation Python applications plus a Vite SPA web application. Python projects are coordinated by one uv workspace and JavaScript projects by one pnpm workspace; the two ecosystems keep separate manifests and lockfiles. `apps/api`, `apps/agent`, and `apps/worker` depend on `packages/medical-core` and the shared `packages/infra` adapter package. Applications never import one another, and each application owns its composition root.

**Amendment (package-boundary refactor):** there is no `packages/contracts` installable package. OpenAPI single-direction generation (ADR 0071) writes TypeScript types into `apps/web` while that remains the only TS consumer; a dedicated contracts package is deferred until a second consumer exists (deletion test). Chat-pipeline orchestration means the deterministic `ChatPipeline` in `medical-core`; the LangGraph `StateGraph` binding stays in `apps/agent`.

## Consequences

- The repository has one root `uv.lock` and one root `pnpm-lock.yaml`; each package still declares its own direct dependencies.
- `medical-core` is a deep domain/application kernel, not a miscellaneous utility package. It owns Ragent-parity medical rules and ports; FastAPI and Aegra own delivery/runtime bindings.
- `packages/infra` is the renamed shared adapter package. It is not nested under `apps/api`, because Agent and Worker need overlapping database, queue, provider, storage, and observability adapters.
- OpenAPI / event contract artifacts live under `apps/web` until a second TypeScript consumer earns a package seam (see ADR 0071 and the amendment above).
- Task orchestration stays inside each ecosystem's native tool: uv runs Python commands, pnpm runs JavaScript/TypeScript scripts. No third-party task runner (e.g. Turborepo) is used — see the amendment below.
- `packages/ui`, `packages/testkit`, `packages/config`, `packages/common`, and `packages/utils` are intentionally absent. Their would-be responsibilities remain local to the consuming app/member or an explicitly owned domain/adapter module.
- The root `docker-compose.yml` remains the deployment boundary; each application directory owns the Dockerfile that builds it.

**Amendment (Turborepo removed):** Turborepo was removed after the single-package workspace made it a no-op. The JavaScript workspace has exactly one member (`apps/web`), so a task graph has nothing to schedule, and local caching cannot pay off when a code change invalidates the only package's cache; the measured difference against direct pnpm invocation was within noise, and CI never had a remote cache to restore from. The web quality gate is now one named script executed by pnpm natively (`pnpm --filter @medicalrag/web run check`), which is the same command CI and documentation use. Reintroduce a task runner only when a second JavaScript member exists or a remote cache can actually serve CI.
