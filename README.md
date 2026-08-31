# MedicalRAG

**证据优先（evidence-first）的医疗知识工作台** —— 面向临床医生、研究者与知识维护者的聊天工作台 + 运营后台：探索经整理的医学知识，绝不把无证据支持的内容当作诊断或处方呈现。

MedicalRAG 以 **行为对齐（behavioral parity）** 方式复刻 Ragent RAG 平台（Java 参考实现），技术栈为 Python 3.14：FastAPI、LangGraph/Aegra、Qdrant Hybrid Retrieval 与 TaskIQ 摄取管线。数据保留在运营方自有基础设施上；每条回答都可溯源至证据，并受安全边界约束。

> **安全边界（Safety Boundary）** —— 回答按医疗风险等级与可用 Evidence 受限；被禁止的个体化请求在检索前短路。MedicalRAG 是可靠的知识助手，绝不是自主临床决策者。

## 为什么

- **证据即界面。** 溯源、出处与引用标签始终可达；检索与安全状态显式呈现，绝不隐藏。
- **克制即权威。** 单一功能色、发丝边框卡片、暖纸壳 —— 工具隐入任务本身（见 [DESIGN.md](DESIGN.md)）。
- **行为对齐，而非代码移植。** 保留参考系统可观察的用户、运营、事件、数据契约与失败行为，技术栈可不同（[ADR 0049](docs/adr/0049-ragent-capability-complete-migration-matrix.md)）。
- **临床级清晰。** 高对比、密度适中且可读的运营表格、固定字号，安全边界是出现时最显眼的元素。

## 功能特性

- **聊天工作台** —— 流式 Evidence Answer、引用、追问连续性，以及不改变安全边界的 Analysis Depth 选项（加深检索预算）。
- **Hybrid Retrieval** —— Qdrant dense + 静态 sparse/BM25 的 RRF 融合，确定性 Evidence Fusion，外部 Reranker（按 Embedding Schema Version 隔离）。
- **运营后台** —— 文档摄取、Chunk 检视、意图树编辑（g6）、模型健康与指标（recharts）。
- **多模态摄取** —— MinerU 驱动的 9 阶段 TaskIQ 管线 + 事务性 outbox、不可变的 Extraction Artifact、经审核的 Published Version。
- **知识隔离** —— Workspace 隔离私有知识；System Knowledge 只读且经评审发布。
- **应用自有身份** —— Argon2id 认证、服务端 Redis 会话、Workspace 角色与记录级所有权。
- **可观测性** —— 结构化日志（loguru）、指标、健康检查，以及可选的 fail-open 自托管 Langfuse Trace 后端。

## 技术栈

| 层 | 选型 |
|---|---|
| 语言 / 运行时 | Python 3.14（uv workspace）、Node 24（pnpm workspace） |
| 后端 | FastAPI · Pydantic v2 · SQLAlchemy 2 + Alembic · PostgreSQL 18 · Redis 8 · TaskIQ + 事务性 outbox |
| 检索 | Qdrant 1.18（dense + sparse/BM25，RRF）· fastembed 静态 sparse · 外部 Reranker |
| Agent | LangGraph / Aegra · Agent Protocol v2 流式（`/api/agent`）· Langfuse OTLP |
| 前端 | React 19 · Vite 8 · TanStack Router / Query / Table · assistant-ui · Tailwind CSS v4 · recharts · @antv/g6 |
| 文档预览 | pdfjs-dist（PDF）· docx-preview（DOCX）· SheetJS + TanStack Table（XLSX） |
| 基础设施 | Docker Compose（根入口）· Nginx 同源反代 · 可选 ClickHouse + Langfuse observability profile |

依赖钉版与实现门禁：见 [docs/version-baseline.md](docs/version-baseline.md)。

## 仓库结构

```
MedicalRAG/
├── docker-compose.yml           # 唯一 Compose 入口（默认构建并启动全部服务；observability 可选）
├── pyproject.toml               # uv workspace root（requires-python >=3.14）
├── .python-version              # Python 3.14.x 锁定
├── package.json / pnpm-workspace.yaml / turbo.json   # 仅前端 JS 工具链
├── apps/                        # 可独立部署的应用（互不 import）
│   ├── api/                     #   FastAPI 组合根：认证/业务/管理 API、摄取触发（写 outbox）
│   ├── agent/                   #   Aegra + LangGraph 聊天管线（Thread/Run、v2 流式）
│   ├── worker/                  #   TaskIQ worker：摄取 job + outbox relay（9 阶段）
│   ├── evaluation/              #   隔离评测 runner（确定性检索指标 + 可选 RAGAS）
│   └── web/                     #   Vite SPA（React 19 + TanStack + assistant-ui）
├── packages/                    # 共享包
│   ├── medical-core/            #   领域 seam：实体/状态机/策略/端口（无框架依赖）
│   └── infra/                   #   具体适配器：PG/Redis/Qdrant/provider/存储/可观测
├── infra/                       # 部署资产（Dockerfile）——不是 Python 包
├── docs/                        # spec、architecture、规范、ADR、research、wayfinder
└── scripts/                     # ci/ dev/ codegen（OpenAPI → TS）
```

约定：`apps/*` 互不 import；共享行为经 `medical-core` / `packages/infra`；`medical-core` 不依赖任何框架（FastAPI/LangGraph/SQLAlchemy/…）。

## 快速开始

前置：Python 3.14 + [uv](https://docs.astral.sh/uv/)、Node ≥ 24.18 + pnpm ≥ 12、Docker Compose ≥ 5.3。

```bash
# 1. 安装依赖
uv sync --locked
pnpm install --frozen-lockfile

# 2. 构建并启动完整栈（PostgreSQL、Redis、Qdrant、api、agent、worker、web）
docker compose up -d
#   ...需要自托管 Langfuse 可观测时：
docker compose --profile observability up -d

# 3. 导出 OpenAPI 并校验生成的 TS 类型（ADR 0071）
uv run --package medicalrag-api python scripts/dev/export_openapi.py
pnpm --filter @medicalrag/web contract-check

# 4. 运行检索评测 runner
uv run --package medicalrag-evaluation python \
  -m medicalrag_evaluation.run eval-retrieval apps/evaluation/fixtures/retrieval.jsonl
```

> Windows 上本地服务与 dev 代理 target 优先用 `127.0.0.1`（如 `MEDICALRAG_API_URL=http://127.0.0.1:8000`）——`localhost` 可能解析为 `::1` 导致挂起。

## 测试与门禁

- **测试金字塔** —— 单元（领域规则/状态机，内存适配器）→ 契约（FastAPI OpenAPI、事件 envelope、Agent Protocol v2、provider 适配器）→ 集成（Compose `test` profile：PG/Redis/Qdrant/TaskIQ+outbox）→ E2E（Playwright：登录、聊天、证据、反馈、管理）。
- **检索评测** —— 每个 PR 跑 `eval-retrieval`（Recall@k、MRR/nDCG、intent Top-1、空召回率、P95）；发布候选跑 `eval-answer`（RAGAS）。任何 RAGAS 分数都不能替代专家安全审核。
- **门禁** —— 提交级：格式/lint/typecheck/单元；PR 级：+ 契约测试 + `eval-retrieval` + 受影响前端构建；合并/发布：+ Compose 集成 + 迁移测试 + E2E + `eval-answer` + 镜像构建。
- **契约门禁** —— `pnpm --filter @medicalrag/web contract-check` 检测 OpenAPI→TS 漂移。
- **parity 判据** —— 某能力只有在其迁移矩阵行（stack + behavior）有通过 fixture 才算 parity-complete。

## 文档

| 文档 | 用途 |
|---|---|
| [CONTEXT.md](CONTEXT.md) | 领域术语正名 / 违禁词（最高优先级）|
| [PRODUCT.md](PRODUCT.md) | 产品定位、品牌 |
| [DESIGN.md](DESIGN.md) | 设计系统 |
| [docs/spec.md](docs/spec.md) | 规范 |
| [docs/architecture.md](docs/architecture.md) | 架构 |
| [docs/development-standards.md](docs/development-standards.md) | 编码规范（强制）|
| [docs/version-baseline.md](docs/version-baseline.md) | 依赖钉版基线 + 门禁 |
| [docs/adr/](docs/adr/) | 架构决策记录（0001–0076）|
| [docs/wayfinder/map.md](docs/wayfinder/map.md) | 决策追踪（权威计划）|
| [docs/reference/stack-replacement-matrix.md](docs/reference/stack-replacement-matrix.md) | 技术栈替换矩阵 |
| [docs/reference/behavior-parity-matrix.md](docs/reference/behavior-parity-matrix.md) | 行为对齐矩阵 |

## 现状

核心基础设施（PostgreSQL/Redis/Qdrant）与仓库骨架已就绪；应用服务（api/agent/worker/web）处于开发中。这是内部研究性复刻实现，不用于临床部署。

## License

尚未声明。
