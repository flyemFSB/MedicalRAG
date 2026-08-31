---
status: accepted
updated_by: ADR-0075
---

# docker-compose.yml is the deployment entrypoint

> **2026-08 更新**：核心服务拓扑已随 [ADR 0075](0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md) 调整为 PostgreSQL/Redis/Qdrant 三核心（Qdrant 单容器，无 MinIO/etcd）；worker 进程由 arq 改为 TaskIQ（ADR 0073）。本条后果中的服务清单以根 `docker-compose.yml` 实际内容为准。

> **2026-08 更新**：应用服务（api/agent/worker/web）不再由 `dev`/`test`/`prod` profile 门控，根 `docker compose up -d` 默认构建并启动全部中间件与应用服务（本地一键起全套）。Aegra 使用独立库 `medicalrag_aegra`（由幂等的 `db-init` 一次性服务创建），避免与 API 的 alembic 迁移链混库。自托管 Langfuse 仍为可选 `observability` profile（ADR 0072）。

The repository-root `docker-compose.yml` is the canonical Docker Compose entrypoint. It defines the application and infrastructure service contracts once and uses `dev`, `test`, and `prod` profiles for environment-specific activation, resource settings, Langfuse configuration, structured logging, metrics, and persistence. It does not add a separate Collector/Tempo/Grafana tracing stack. The project uses the modern `docker compose` command while retaining the requested hyphenated filename.

## Consequences

- Service names, private networks, health checks, dependency readiness, named volumes, and required environment variables are stable across profiles.
- Local Compose provisions PostgreSQL, Redis, Milvus and its dependencies, MinIO, FastAPI, Aegra server/worker, the arq worker, and the Vite SPA web service (Nginx); model, embedding, reranker, and MinerU providers remain external APIs. No RocketMQ broker is provisioned.
- Test profiles may replace external services with deterministic fixtures only where the contract explicitly permits it; production profiles cannot silently downgrade durable dependencies to in-memory processes.
- Additional Compose fragments may be introduced only as implementation details or CI overrides; user-facing startup documentation continues to use `docker-compose.yml`.
