# Ragent → MedicalRAG Stack Replacement Matrix

Deep-check result: every audited component of `D:\yzb\ragent` has an explicit target-stack replacement, adaptation, or rejection in the MedicalRAG plan. The behavioral dimension (streaming events, failure behavior, admin console routes) lives in [behavior-parity-matrix.md](behavior-parity-matrix.md); together they form the `ragent-capability-complete-migration-matrix` release gate. Status values follow [ADR 0049](../adr/0049-ragent-capability-complete-migration-matrix.md): `implemented`, `replaced`, `adapted`, `rejected`.

## Backend and runtime

| Ragent component | Source version | Target in MedicalRAG | Status |
|---|---|---|---|
| Language runtime | Java 17 | Python 3.14 via uv ([ADR 0064](../adr/0064-uv-manages-python-314-runtime.md)) | replaced |
| Web framework | Spring Boot 3.5.7 | FastAPI + Aegra (Agent Protocol v2) | replaced |
| ORM | MyBatis-Plus 3.5.14 | SQLAlchemy 2 async + Alembic | replaced |
| Business database | PostgreSQL (20 tables) | PostgreSQL (full migration coverage) | implemented |
| Vector database | Milvus SDK Java 2.6.6 | Qdrant, dense + sparse/BM25 Hybrid Retrieval via fastembed ([ADR 0075](../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)) | replaced |
| Document parsing | Apache Tika 3.2.3 + MinerU | MinerU external API ([ADR 0014/0015/0016/0032](../adr/0014-mineru-is-the-primary-multimodal-extraction-engine.md)) | replaced |
| Object storage | AWS S3 2.40.2 + Aliyun OSS 3.18.5 | `ObjectStorage` port behind a local filesystem adapter in v1 (Qdrant removed MinIO from Compose, [ADR 0075](../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)) | replaced |
| Authentication | Sa-Token 1.43.0 + Redis | Application-owned Argon2id + Redis sessions ([ADR 0018](../adr/0018-application-owned-authentication.md)) | replaced |
| Redis client | Redisson 4.0.0 | redis-py | replaced |
| **Message bus** | **RocketMQ** spring-boot-starter 2.3.5 | **TaskIQ (Redis job queue) + PostgreSQL outbox** ([ADR 0073](../adr/0073-taskiq-replaces-arq-as-the-durable-job-queue.md)) | replaced |
| HTTP client | OkHttp 4.12.0 | httpx | replaced |
| Utility library | Hutool 5.8.37 | Python standard library / small helpers | replaced |
| Operation log | bizlog-sdk 3.0.6 | PostgreSQL audit events + `run_events` | replaced |
| Context propagation | Transmittable ThreadLocal 2.14.5 | asyncio + structured `request_id`/`run_id` correlation | replaced |
| Distributed ID | Snowflake (framework) | UUIDv7 via Python 3.14 `uuid.uuid7()` ([ADR 0066](../adr/0066-uuidv7-is-the-universal-business-identifier.md)) | replaced |
| MCP Server/Client | MCP SDK 1.1.2 | Rejected (out of scope, ADR 0051) | rejected |

## Concurrency and reliability

| Ragent component | Source version | Target in MedicalRAG | Status |
|---|---|---|---|
| Thread pools (8) + TtlExecutors | — | asyncio + application services; no raw thread pools | replaced |
| Queue-based concurrency limiter | Redis ZSET + Lua + Pub/Sub | Redis rate limiting + queued-request status events (user story 29) | replaced |
| Three-state circuit breaker | — | Redis-backed model health circuit | replaced |
| First-token probing | ProbeBufferingCallback | External model streaming with cancellation and failover | replaced |
| Idempotency (framework) | double-dimension | PostgreSQL unique constraints + stable job ids | replaced |

## Retrieval, intent, and generation

| Ragent component | Target in MedicalRAG | Status |
|---|---|---|
| Multi-channel retrieval + post-processors | Qdrant Hybrid Retrieval + Evidence Fusion (deterministic) | replaced |
| pgvector vector store | Rejected — Qdrant is the sole retrieval engine ([ADR 0075](../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)) | rejected |
| Elasticsearch keyword store | Rejected — Qdrant sparse/BM25 + PostgreSQL filtering | rejected |
| Neo4j graph query | Rejected — application-owned Structured Medical Metadata (graph service excluded) | rejected |
| LightRAG | Rejected | rejected |
| Reranker | External Reranker API (ADR 0037) | replaced |
| Dynamic intent tree | PostgreSQL intent-tree nodes + Redis cache + LLM classification | implemented |
| Ambiguity guidance | Ambiguity service, bounded user choices | implemented |
| Slot extraction | Application-owned structured output (not MCP) | implemented |
| Query rewrite + split | Rewrite/split stage with pronoun resolution | implemented |
| Model routing + health | External Model Router + Redis circuit | replaced |
| LLM generation | External Generation Provider streaming (ADR 0007/0009) | replaced |
| Ollama / local models | Rejected — external APIs only | rejected |
| Memory compression/summary | Bounded window + durable summary | implemented |

## Frontend and observability

| Ragent component | Source version | Target in MedicalRAG | Status |
|---|---|---|---|
| UI framework | React 18 + Vite + TS 5.5 | React + Vite SPA + TS 6 + assistant-ui；Nginx/Vite 同源代理，无 SSR（[ADR 0070](../adr/0070-vite-spa-with-nginx-proxy-is-the-frontend-runtime.md)）| replaced |
| Markdown + GFM rendering | commonmark, react-markdown + remark-gfm | react-markdown + remark-gfm | implemented |
| Auth/security headers | — | Same-origin entrypoint, secure cookies, validation | implemented |
| SSE streaming | SseEmitterSender | Aegra v2 SSE / direct streaming | replaced |
| Admin dashboard charts | recharts 3.7, @antv/g6 5.1 | recharts (dashboard KPIs) + @antv/g6 (intent-tree editor) ([ADR 0067](../adr/0067-operator-console-charting-recharts-and-g6.md)) | replaced |
| Document preview | @js-preview/excel 1.7 | pdfjs-dist (PDF) + docx-preview (docx) + SheetJS/TanStack Table (xlsx)；pptx v1 为 typed unsupported（[ADR 0068](../adr/0068-document-preview-mainstream-per-format-renderers.md)）| replaced |
| Deep-thinking mode | frontend toggle | Analysis Depth per-request option ([ADR 0069](../adr/0069-deep-thinking-is-analysis-depth-option.md)) | replaced |
| Forms/validation | react-hook-form + zod | zod (or approved equivalent) | replaced |
| Tables | @tanstack/react-table | TanStack Table (or approved equivalent) | replaced |
| Trace | AOP @RagTraceNode | Aegra official Langfuse integration (ADR 0062) | replaced |
| Feedback | thumbs up/down | PostgreSQL feedback records | implemented |

## Tooling and deployment

| Ragent component | Source version | Target in MedicalRAG | Status |
|---|---|---|---|
| Build tool | Maven + Spotless | uv + uv workspace; frontend pnpm + Turborepo | replaced |
| Deployment | docker-compose (rocketmq-stack, milvus-stack) | Root `docker-compose.yml` with `dev`/`test`/`prod` profiles; no RocketMQ service, no Milvus/MinIO (Qdrant single-container core) | replaced |
| Package mirrors | — | Aliyun mirrors for pnpm/uv/apt ([ADR 0065](../adr/0065-aliyun-mirrors-for-pnpm-uv-and-apt.md)) | implemented |

## Resolved gaps

The four gaps identified by the deep-check are closed by ADR 0066–0069: distributed ID generation (UUIDv7), operator console charting (recharts + @antv/g6), document preview (mainstream per-format renderers, ADR 0068), and deep-thinking mode (Analysis Depth). No unresolved stack-replacement gaps remain; the migration matrix release gate can now track only row-by-row implementation status.
