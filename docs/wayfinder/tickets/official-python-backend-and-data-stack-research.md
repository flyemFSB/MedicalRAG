---
kind: ticket
label: wayfinder:research
status: closed
parent: ../map.md
assignee: codex
depends_on: []
research_file: ../../research/python-backend-and-data-stack.md
title: Official Python backend and data-stack research
---

## Question

What do the official documents for Python 3.14, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL, Redis/redis-py, and arq recommend for project layout, async I/O, configuration, dependency injection, migrations, connection management, transactions, retries, idempotency, testing, and production operation?

## Reconciliation

The original research question and its [research document](../../research/python-backend-and-data-stack.md) were written for Python 3.12 and Apache RocketMQ. The plan now uses Python 3.14 ([ADR 0064](../../adr/0064-uv-manages-python-314-runtime.md)) and arq ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)). The research document remains a historical snapshot; its conclusion on messaging is superseded by the arq/outbox contract and its Python-version guidance is re-run against 3.14 before implementation.

## Resolution

Research complete and reconciled. The research document captured the official guidance for the Python data stack and now carries a supersession note. Reconciled to the current plan: Python 3.14 via uv ([ADR 0064](../../adr/0064-uv-manages-python-314-runtime.md)), arq + PostgreSQL transactional outbox replacing RocketMQ ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)), Aliyun mirrors for pnpm/uv/apt ([ADR 0065](../../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md)). The stack-optimality evaluation is captured in [tech-stack-objective-evaluation](../../research/tech-stack-objective-evaluation.md) §1. Implementation gates remain: verify cp314 wheels (asyncpg ≥0.31.0, hiredis ≥3.3.0, grpcio ≥1.81.0, SQLAlchemy ≥2.0.47) and the aegra-api 3.14 baseline.
