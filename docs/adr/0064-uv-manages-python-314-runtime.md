---
status: accepted
---

# uv manages a Python 3.12 runtime baseline

**Amendment:** MedicalRAG's Python runtime baseline is **3.12** (`.python-version` pins 3.12.x for Docker, CI, and development). The earlier 3.14 baseline is superseded.

UUIDv7 remains the universal business identifier (ADR 0066). Because `uuid.uuid7()` is stdlib-only from 3.14, `packages/medical-core` ships a stdlib RFC 9562 implementation at `medicalrag_core.ids.uuid7`; all call sites use that helper. This keeps `medical-core` free of third-party runtime dependencies.

Every Python workspace member declares `requires-python >=3.12` (lower bound only, following uv's documentation convention). Aegra, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, redis-py, and TaskIQ all support 3.12.

## Consequences

- The uv lockfile is regenerated against Python 3.12; every member's `requires-python` is `>=3.12`; root `.python-version` pins 3.12.x.
- Docker base images use `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`.
- Ruff `target-version = "py312"`; pyright `pythonVersion = "3.12"`.
- Business IDs use `medicalrag_core.ids.uuid7`, not `uuid.uuid7`.
- The 3.14 decision recorded in historical research snapshots is superseded by this amendment.
