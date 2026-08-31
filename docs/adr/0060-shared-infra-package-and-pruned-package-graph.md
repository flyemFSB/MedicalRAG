---
status: accepted
---

# Keep shared adapters in `packages/infra` and prune speculative packages

The Python monorepo contains three shared packages: `packages/medical-core`, `packages/infra`, and `packages/contracts`. The Python import package uses the project-qualified name `medicalrag_infra` rather than the generic `infra` import name.

`packages/infra` is not moved into `apps/api`. API, Agent, and Worker all need overlapping concrete adapters for PostgreSQL, Redis, Milvus, object storage, external providers, structured logging, metrics, health, and, for Worker, arq. Putting these adapters under API would force other runtimes to import an application package, duplicate implementations, or add an unnecessary internal HTTP hop. Each app owns only its composition root and declares the adapter extras it uses. Aegra owns its official Langfuse integration; `packages/infra` does not own an application-wide Trace provider.

The repository-level `infra/` directory remains reserved for Dockerfiles, Compose initialization, and service configuration. It is distinct from the installable Python package at `packages/infra/`.

## Removed packages

- `packages/ui`: the only web app owns its components under `apps/web/src/components` and feature modules.
- `packages/testkit`: fakes, fixtures, and test builders live beside the member whose interface they exercise; shared wire fixtures live under `packages/contracts`.
- `packages/config`: runtime settings are owned by `apps/api`, `apps/agent`, `apps/worker`, and `apps/web` because deployment scope and secret ownership differ.
- `packages/common` and `packages/utils`: code must be placed in the domain or adapter module that owns its meaning; no generic dumping-ground package is created.

## Deletion test

Deleting `medical-core` would duplicate medical invariants across three runtimes, so it earns its seam. Deleting `infra` would duplicate provider/database semantics or couple applications through API imports, so it earns its seam. Deleting the proposed UI, testkit, config, common, and utils packages removes indirection without removing behavior; they do not earn standalone seams at this stage.

## References

- [Python Packaging User Guide: `src` layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [FastAPI bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
