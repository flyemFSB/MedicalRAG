---
status: accepted
related:
  - 0059-langfuse-is-a-fail-open-operational-observability-sink
  - 0062-langfuse-is-the-only-ai-rag-trace-backend
  - 0072-langfuse-self-hosted-optional-observability-profile
  - 0076-aegra-owns-langfuse-ingestion-via-otlp
---

# Phoenix replaces Langfuse as the self-hosted observability backend

The optional `observability` Compose profile self-hosts **Arize Phoenix**（单容器）instead of the Langfuse v3/v4 stack（langfuse-web + langfuse-worker + ClickHouse，官方口径还需 Redis 与 S3/MinIO）。动机：AI/RAG 观测在本项目的强诉求是 **agent eval**（回放 Run、标注、数据集与实验），而 Langfuse 自托管栈为高吞吐生产观测设计，官方最低配合计 +4–8 GiB 内存与 ClickHouse 磁盘负担；Phoenix 单容器（官方 sizing ~1 GB 常驻 + 每百万 trace 约 1 GB）覆盖同一诉求，且自托管免费无功能阉割、可完全 air-gap（数据不出运营网络，延续 ADR 0072 的 data-sovereignty 立场）。

后端按官方 Docker 部署最佳实践切到 **PostgreSQL**（官方支持 PG ≥ 14）：`PHOENIX_SQL_DATABASE_URL` 指向主栈 postgres 实例的独立库 `medicalrag_phoenix`（由幂等 `db-init` 创建，与 `medicalrag`/`medicalrag_aegra` 同实例不同库）——零新增中间件，备份策略与主库一致。

## Rationale

- **摄取通路不变**：aegra 0.10.4 原生支持 `OTEL_TARGETS=PHOENIX`（`PHOENIX_COLLECTOR_ENDPOINT` + 可选 `PHOENIX_API_KEY` Bearer 头），与 Langfuse 同为 OTLP HTTP 导出；ADR 0076 的「Aegra 唯一摄取 owner / fail-open / 应用不自建 exporter 与 span tree」原则全部保留。aegra 的 `SpanEnrichmentProcessor` 会同时写通用语义属性（`user.id`、`session.id`），对 Phoenix 同样生效。
- **Run ↔ 观测关联键**：一次 Run 在 Phoenix 中不是单条 trace（aegra 不创建 Run 级 span），而是经 `session.id`（= Aegra `thread_id`）聚合的 Session。`chat_runs.langfuse_trace_id` 改名为 `chat_runs.trace_id`，语义改为「Aegra thread_id（Phoenix session id）」；orchestrate 节点从 LangGraph run config 读取 `configurable.thread_id` 写入（此前该值无人赋值，链路关联实际处于休眠）。运营深链用 Phoenix 官方重定向路由 `/redirects/sessions/{session_id}`，无需 Phoenix 内部 UUID。
- **反代**：Nginx 新增 `/phoenix/` → `phoenix:6006`，Phoenix 侧 `PHOENIX_HOST_ROOT_PATH=/phoenix` 使 UI 资源与重定向按子路径生成。
- **安全**：启用 profile 时 `PHOENIX_ENABLE_AUTH=true` + `PHOENIX_SECRET`（签发 JWT）；运营以 `admin@localhost` 首启登录改密后创建 system API key，经 `PHOENIX_API_KEY` 注入 aegra 导出鉴权。医疗内容脱敏继续依赖 Aegra 默认脱敏观测字段与 Data Egress Policy（ADR 0076 修正口径，非 `mask_otel_spans`）。

## Consequences

- `observability` profile 从 3 容器（clickhouse + langfuse-web + langfuse-worker）降为 1 容器，ClickHouse 移除；profile 内存预算从 +4–8 GiB 降到 ~1 GiB。未启用 profile 时 `OTEL_TARGETS` 为空，agent 零导出开销（fail-open 语义不变）。
- 吞吐上限低于 Langfuse/ClickHouse（Phoenix 单节点）；eval 与小团队运营远够用，增长期可加 Postgres 读副本（`PHOENIX_SQL_DATABASE_READ_REPLICA_URL`）或届时再评估 Langfuse Cloud。
- Trace 保留期钉 `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=90`（延续 ADR 0072 有界保留），可经 .env 调整。
- 评测指标真相源仍是 `apps/evaluation` 的确定性 runner 与 RAGAS（ADR 0049 门禁）；Phoenix 承担 trace 收集、数据集与实验编排，不替代安全专家审核。
- CONTEXT.md 的 Trace 正名同步改为后端中立表述（不再绑定 Langfuse）。

## References

- [Phoenix self-hosting configuration](https://arize.com/docs/phoenix/self-hosting/configuration)（`PHOENIX_SQL_DATABASE_URL`、`PHOENIX_HOST_ROOT_PATH`、retention）
- [Phoenix Docker deployment](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker)（PostgreSQL backend、pin 版本最佳实践）
- [Phoenix authentication](https://arize.com/docs/phoenix/self-hosting/features/authentication)（`PHOENIX_ENABLE_AUTH`/`PHOENIX_SECRET`/system API key）
- [Phoenix shareable URLs](https://arize.com/docs/phoenix/tracing/how-to-tracing/advanced/constructing-urls)（`/redirects/traces|sessions/{id}`）
- aegra `aegra_api/observability/targets/phoenix.py` 与 `span_enrichment.py`（0.10.4，verified 2026-08-29）
