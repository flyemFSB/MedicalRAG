---
kind: ticket
label: wayfinder:grilling
status: closed
parent: ../map.md
assignee: codex
depends_on:
  - aegra-fastapi-arq-worker-runtime-contract.md
  - ingestion-and-mineru-state-machine.md
  - monorepo-toolchain-and-package-boundaries.md
  - official-devops-quality-security-and-observability-research.md
title: Compose profiles and operational topology
---

## Question

What services, profiles, networks, volumes, health/readiness checks, startup ordering, backups, observability, scaling, upgrade policy, and package-mirror configuration belong in the root `docker-compose.yml`? RocketMQ is not provisioned: the arq worker and its Redis transport replace the broker, and pnpm/uv/apt use Aliyun mirrors for development, CI, and image builds.

## Resolution

- **Canonical entrypoint** — the repository-root `docker-compose.yml` is the single Compose entrypoint ([ADR 0053](../../adr/0053-docker-compose-yml-is-the-deployment-entrypoint.md)); production differences use `-f compose.production.yaml` overrides rather than redefining the base.
- **Core services (no profile, always on)** — PostgreSQL 18.4, Redis 8.10, Milvus standalone with etcd metadata (per [ADR 0026](../../adr/0026-milvus-standalone-is-the-compose-vector-store.md)), and MinIO pinned to the last AGPL release with isolated Milvus storage ([ADR 0017](../../adr/0017-s3-compatible-object-storage-with-minio.md), [ADR 0027](../../adr/0027-shared-minio-instance-with-isolated-milvus-storage.md)). Core services are deliberately not behind a profile so the `test` profile still reaches the database.
- **Application services** — `api` (FastAPI), `agent` (Aegra server), `worker` (arq Worker), and `web` (the Vite SPA build served by Nginx, which proxies `/api` → api and `/api/agent` → agent, [ADR 0070](../../adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)). No RocketMQ broker is provisioned ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)).
- **Profiles** — `dev` (hot reload and debug; the Vite dev server runs on the host with `server.proxy`, backend hot-reload via Compose Watch); `test` (integration/contract test runners plus Playwright; core services remain on); `prod` (app containers, Nginx, production logging/metrics/health). Langfuse stays SaaS or an optional `observability` profile, not a mandatory Compose service ([ADR 0062](../../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md)).
- **Networks / volumes / readiness** — one private network; named volumes for PostgreSQL data, Redis persistence, MinIO objects, and Milvus storage/metadata; healthchecks on every core service; `depends_on` uses `condition: service_healthy`; liveness vs readiness are separate per process.
- **Startup ordering / backups** — apps wait on healthy core dependencies; backups coordinate PostgreSQL (base backup + WAL/PITR), MinIO objects, and Milvus (rebuilt from immutable ingestion artifacts via the publication manifest) rather than snapshotting the cluster blindly.
- **Observability / scaling / upgrade** — structured logs, metrics, and health checks; no Collector/Tempo/Grafana ([ADR 0062](../../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md)); worker and agent scale horizontally via Redis leases; all image tags pinned (no `latest`), and upgrades are lockfile-driven with a re-run of the Compose `test` profile as the gate.
- **Package mirrors** — pnpm/uv/apt use Aliyun mirrors in dev, CI, and image builds ([ADR 0065](../../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md)); Docker image pulls use a pinned registry/ACR strategy because the Aliyun public acceleration no longer mirrors the latest images.
