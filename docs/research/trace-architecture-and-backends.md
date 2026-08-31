# MedicalRAG Trace 方案调研与决策

> 调研日期：2026-07-27  
> 文档性质：官方资料调研、候选方案比较和当前实现边界。当前决策以 [ADR 0062](../adr/0062-langfuse-is-the-only-ai-rag-trace-backend.md) 为准。

> **计划变更（2026-08-01）：** 按 [ADR 0063](../adr/0063-arq-replaces-rocketmq-as-the-durable-job-queue.md) 消息总线已从 Apache RocketMQ 更换为 arq；正文中“HTTP/SQL/Redis/Milvus/RocketMQ”等跨基础设施 Trace 表述中的 RocketMQ 应读作 arq，且该设计方向仍被 ADR 0062 拒绝。

## 1. 结论

本项目不部署独立的系统级分布式 Trace 平台。Aegra 的官方 Langfuse 集成是唯一的 AI/RAG Trace 路径；API、Worker 和领域服务使用结构化日志、指标、健康检查及 PostgreSQL 业务运行记录完成基础运维诊断。

```text
Aegra graph/LLM
    -> official Langfuse integration
    -> Langfuse: redacted AI/RAG observations

FastAPI / Worker / domain services
    -> structured JSON logs + metrics + health checks

PostgreSQL
    -> chat_runs / ingestion_runs / run_events / audit_events
    -> optional langfuse_trace_id correlation
```

这不是“完全没有 Trace”，而是只保留对 RAG 调试和模型调用最有价值的 Langfuse Trace，不再维护第二套基础设施 Trace 事实源。

## 2. 候选技术的官方事实

### 2.1 OpenTelemetry

OpenTelemetry 提供 API、SDK、instrumentation、OTLP、语义约定和 Collector，可覆盖 HTTP、数据库、缓存、消息、外部 API 等系统边界。Collector 可以承担批处理、重试、采样、脱敏和路由。

这些能力适合复杂微服务、跨服务 SLO、基础设施性能排障和统一 logs/metrics/traces 平台，但会引入 SDK、上下文传播、Collector、后端存储、查询 UI、采样、保留和数据脱敏等额外运营面。

### 2.2 Tempo、Jaeger 和 Grafana

Grafana Tempo 适合以对象存储为基础的 Trace 后端；Jaeger v2 是成熟的分布式 Trace 方案，但生产存储和查询拓扑需要单独规划。它们都解决的是系统调用链问题，不是 RAG 语义分析、Token/成本、模型版本和检索观察问题。

本项目已经决定不引入 Elasticsearch 作为观测依赖，也没有当前规模所需的跨服务 Trace 运维需求，因此 Tempo、Jaeger 和 Grafana 只保留为未来升级候选，不加入 Compose。

### 2.3 Aegra 与 Langfuse

Aegra 官方文档说明其 observability 基于 OpenTelemetry，并支持 Langfuse、Generic OTLP 等 target。Langfuse 官方提供 Python SDK、统一 observation API、LangChain/LangGraph 集成、原生 OTLP 入口、脱敏、采样和异步 fail-open 导出能力。

Aegra 已经拥有 Agent graph/LLM 的运行上下文和官方观测出口。应用再添加 LangChain `CallbackHandler`、手动 span 或第二个 exporter 会产生重复 observation，且违反“不自定义 runtime”的边界。

## 3. 为什么 Langfuse-only 足够

当前系统的主要观测问题是：

- 查询改写、意图识别、slot 提取、检索、重排、证据组装和模型生成是否按预期执行。
- 外部模型的耗时、Token、模型版本、失败类型和 fallback 是否可解释。
- Ragent 的业务运行阶段、错误和安全策略版本是否可审计。

这些信息属于 Agent/RAG 语义观测，Langfuse 可以在 Aegra 托管的 graph/LLM 执行上下文中提供对应视图。API、Worker、数据库、Redis、Milvus 和 RocketMQ 的健康与性能问题，则由结构化日志、指标、健康检查和各自管理工具处理。

## 4. 明确的职责边界

| 组件 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| Aegra 官方 Langfuse 集成 | graph/LLM、retrieval 相关安全元数据、耗时、状态、Token/成本等 AI/RAG observation | 业务事务、权限、Conversation source of truth |
| Langfuse | AI/RAG Trace 查询、generation/agent 分析、评分与评测关联 | HTTP/SQL/Redis/Milvus/RocketMQ 的完整基础设施调用链 |
| PostgreSQL | `chat_runs`、`ingestion_runs`、`run_events`、审计、状态、版本、计数和可选 trace id | Langfuse observation/span 树 |
| API/Worker | 结构化日志、指标、readiness/liveness、错误码和安全 correlation fields | 自建 Trace runtime、手动 span 树、第二个 Langfuse client |
| Agent Protocol v2 | thread、run、command、SSE streaming 和重连合同 | Trace 存储和查询 |

`run_id` 是业务主键；`langfuse_trace_id` 只是可丢失、可过期的观测关联值。业务状态不能依赖 Langfuse 是否可用。

## 5. Langfuse 实现约束

1. 只由 Aegra 初始化和配置 Langfuse；FastAPI、Worker、`packages/infra` 和普通 domain service 不创建 Langfuse client。
2. 不在 LangGraph 入口额外注入 Langfuse `CallbackHandler`，不添加手写 `start_observation()` 包装器，不实现自定义 runtime 或 exporter。
3. 默认只发送服务、环境、代码/模型/provider 版本、operation、耗时、状态、重试次数、Token/count、策略版本、错误类别和已批准的安全 ID。
4. 禁止发送原始 prompt、医疗问题、完整模型输出、文档/chunk/evidence 文本、患者标识、Cookie、Authorization、API key、连接字符串、provider response body 和 hidden chain-of-thought。
5. Aegra 的 Langfuse exporter 必须异步、有界、带超时，并在认证错误、429、5xx、DNS、队列满或 flush 失败时 fail-open。降级只记录非敏感日志和指标。
6. Langfuse Cloud 或官方 self-hosted Compose 的选择由数据出境、保留、访问控制、备份、灾备和医疗合规要求决定。Compose self-hosted 不自动提供 HA、横向扩展或备份。

## 6. PostgreSQL 业务记录

保留以下业务表或等价模型：

```text
chat_runs
ingestion_runs
run_events
audit_events
```

建议字段包括 `run_id`、workspace/user scope、状态、开始/结束时间、阶段耗时、policy/version、safe counts、failure code、actor 和可选 `langfuse_trace_id`。这些记录用于产品状态、审计、重试和管理端导航，不复制 Langfuse observation attributes，也不保存完整 prompt、证据或模型输出。

如果 Langfuse 不可用，业务运行仍应完成状态持久化；管理端展示“AI/RAG 观测不可用”，而不是把业务运行标记为失败。

## 7. 影响和升级条件

### 已接受的影响

- 无法从一个 Trace UI 查看 API -> SQL -> Redis -> Milvus -> RocketMQ -> provider 的完整分布式调用链。
- Langfuse 是 AI/RAG 观测的外部依赖，故障时详细 Trace 可能缺失。
- Langfuse 的数据出境、访问控制和保留策略必须单独审核。
- 需要依赖结构化日志、指标和服务自身管理界面完成基础设施排障。

### 未来需要增加 OTel 的条件

只有出现以下需求时，才重新评估 OpenTelemetry + Collector + Tempo/Jaeger：

- 多个独立 API、Agent、Worker、网关和消息消费者之间需要跨服务 SLO 分析。
- 需要对 SQL、Redis、Milvus、RocketMQ 和外部 HTTP 调用进行统一尾延迟分析。
- 生产故障需要跨服务 TraceQL/依赖拓扑定位，结构化日志和指标已经不足。
- 合规或平台团队要求统一的组织级分布式 Trace 标准。

当前通过保留 `request_id`、`run_id`、安全日志字段和 `langfuse_trace_id`，为未来接入 OTel 留出关联位置，但不为假设性需求提前引入依赖。

## 8. 测试与发布门禁

- Aegra/Langfuse 合同测试：metadata schema、Trace 关联、redaction、sampling、超时、认证失败、429/5xx、队列满、shutdown flush 和 fail-open。
- 业务测试：Langfuse endpoint 不可用时，聊天、摄取、RocketMQ 状态机和 PostgreSQL 业务记录仍保持正确。
- 日志/指标测试：只允许 `request_id`、`run_id`、安全错误码、耗时、计数和状态等白名单字段。
- 集成测试不启动 Collector、Tempo、Grafana 或 Jaeger；Langfuse 外部依赖使用合同测试替身或隔离的测试环境。
- 医疗数据测试证明 prompt、医疗文本、文档内容、患者标识、凭据和完整模型输出不会进入 Langfuse、日志或测试产物。

## 9. 官方资料

- [Aegra observability](https://docs.aegra.dev/guides/observability)
- [Aegra streaming](https://docs.aegra.dev/guides/streaming)
- [Langfuse Python SDK instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation)
- [Langfuse native OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry)
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking)
- [Langfuse sampling](https://langfuse.com/docs/observability/features/sampling)
- [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
- [OpenTelemetry specification](https://opentelemetry.io/docs/specs/otel/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Grafana Tempo](https://grafana.com/docs/tempo/latest/)
- [Jaeger v2 architecture](https://www.jaegertracing.io/docs/2.20/architecture/)
- [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/)
