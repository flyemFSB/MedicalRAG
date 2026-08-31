---
status: accepted
---

# uv manages a Python 3.14 runtime baseline

MedicalRAG declares Python 3.14 as its Python runtime baseline and uses uv to manage the interpreter, dependencies, virtual environments, and commands. Every Python workspace member (`apps/api`, `apps/agent`, `apps/worker`, `apps/evaluation`, `packages/medical-core`, `packages/infra`, `packages/contracts`) declares `requires-python >=3.14` (a lower bound only, following uv's documentation convention), and a `.python-version` file pins the 3.14 minor baseline shared by Docker, CI, and development machines. This supersedes the earlier Python 3.12 constraint recorded in the research snapshots.

Aegra requires Python `>=3.12`, so 3.14 is inside its declared constraint; FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, redis-py, PyMilvus, and arq are expected to ship 3.14-compatible releases, but each must be verified end-to-end before implementation is declared final.

## Consequences

- The uv lockfile is regenerated against Python 3.14, every member's `requires-python` is aligned to `>=3.14` (lower bound only), and a root `.python-version` file pins the 3.14.x minor baseline.
- Docker base images move to `python:3.14-slim`; CI `python-quality` and integration jobs install Python 3.14 and run `uv sync --locked`.
- The pinned compatibility baseline recorded in `compatibility-openai-and-evaluation.md` (for example FastAPI, SQLAlchemy, PyMilvus, redis-py, and Aegra versions) is re-validated on 3.14; the RocketMQ client entry is removed from the baseline.
- The declared runtime text in the specification, architecture, map, and research reconciliation notes is updated from Python 3.12 to Python 3.14.
- The `python-backend-and-data-stack` and `monorepo-best-practices` research documents remain historical snapshots of the 3.12 decision; their conclusions are reconciled here rather than rewritten in place.
