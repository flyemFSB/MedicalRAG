---
kind: ticket
label: wayfinder:research
status: closed
parent: ../map.md
assignee: codex
depends_on: []
research_file: ../../research/devops-quality-security-and-observability.md
title: Official DevOps, quality, security, and observability research
---

## Question

What do the official documents for Docker Compose, Compose profiles, container health checks, pytest, pytest-asyncio, HTTPX, integration-test tooling, OpenTelemetry, structured logging, Argon2/password hashing, secure cookies, OWASP guidance, and CI workflows recommend for development, testing, security, observability, and release gates?

## Resolution

Research complete and reconciled. The research document captured official guidance for Compose, health checks, test tooling, security, observability, and CI and now carries a supersession note. Reconciled to the current plan: arq replaces RocketMQ ([ADR 0063](../../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md)), Python 3.14 baseline ([ADR 0064](../../adr/0064-uv-manages-python-314-runtime.md)), Aliyun mirrors ([ADR 0065](../../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md)), MinIO pinned to the last AGPL release ([ADR 0017](../../adr/0017-s3-compatible-object-storage-with-minio.md)), and the Vite SPA + Compose core-services-not-on-profiles topology ([ADR 0070](../../adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)). The stack-optimality evaluation is captured in [tech-stack-objective-evaluation](../../research/tech-stack-objective-evaluation.md) §3.5–3.7.
