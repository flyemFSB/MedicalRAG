---
status: accepted
---

# Keep shared adapters in `packages/infra` and prune speculative packages

The Python monorepo contains two shared packages: `packages/medical-core` and `packages/infra` (plus `packages/assembly` for shared composition factories). The Python import package uses the project-qualified name `medicalrag_infra` rather than the generic `infra` import name.

**Amendment:** `packages/contracts` is not an installable package. Generated `/api` TypeScript types live under `apps/web` (single consumer; ADR 0071). Persistence repositories under `infra` are split by domain module (`identity_repos`, `knowledge_repos`, `conversation_repos`, `ops_repos`); `operator.py` remains only the `OperatorRepositories` facade. Ingestion ports (`VectorIndexer`, `ChunkRepository`) live on `medical-core`, not on `apps/worker`.

`packages/infra` is not moved into `apps/api`. API, Agent, and Worker all need overlapping concrete adapters for PostgreSQL, Redis, Milvus, object storage, external providers, structured logging, metrics, health, and, for Worker, arq. Putting these adapters under API would force other runtimes to import an application package, duplicate implementations, or add an unnecessary internal HTTP hop. Each app owns only its composition root and declares the adapter extras it uses. Aegra owns its official Langfuse integration; `packages/infra` does not own an application-wide Trace provider.

The repository-level `infra/` directory was removed (2026-09 amendment): each application owns the Dockerfile that builds it (`apps/<app>/Dockerfile`, same convention as `apps/web/Dockerfile`), and Compose initialization stays solely in the root `docker-compose.yml`. The installable Python package at `packages/infra/` is therefore the only thing named `infra` in the repository.

`packages/assembly` holds composition factories shared by combination roots (currently `build_chat_pipeline`, used by both `apps/api` and `apps/agent`). It depends on `medical-core` and `packages/infra`, carries no adapters or domain logic of its own, and keeps assembly policy out of the adapter package. It is deliberately thin (one factory); it keeps its seam because the two roots must not drift apart, but it is not a home for settings, Docker wiring, or CLI concerns — reassess the seam if it grows beyond composition factories.

## Removed packages

- `packages/ui`: the only web app owns its components under `apps/web/src/components` and feature modules.
- `packages/testkit`: fakes, fixtures, and test builders live beside the member whose interface they exercise; shared wire fixtures stay with the consuming app.
- `packages/config`: runtime settings are owned by `apps/api`, `apps/agent`, `apps/worker`, and `apps/web` because deployment scope and secret ownership differ.
- `packages/common` and `packages/utils`: code must be placed in the domain or adapter module that owns its meaning; no generic dumping-ground package is created.

## Deletion test

Deleting `medical-core` would duplicate medical invariants across three runtimes, so it earns its seam. Deleting `infra` would duplicate provider/database semantics or couple applications through API imports, so it earns its seam. `assembly` earns its seam through shared wiring between two combination roots rather than through size. `apps/evaluation` remains a workspace member because it is a separate runnable entry point whose isolation (optional RAGAS dependencies) is the point — it is retained for near-zero cost, not because it passed a seam test. Deleting the proposed UI, testkit, config, common, and utils packages removes indirection without removing behavior; they do not earn standalone seams at this stage.

Within `medical-core`, module directories are reserved for domains that own several modules; single-concept record entities stay in one flat module (`records.py`) rather than each claiming a directory.

## References

- [Python Packaging User Guide: `src` layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [FastAPI bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
