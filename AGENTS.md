# AGENTS.md — MedicalRAG 项目说明与开发约定

本文件是本仓库唯一开发指令文件（原 `CLAUDE.md` 已并入并移除）。先读本文件，再动手。

开始任何写、改、修、重构、审代码工作前，按优先级阅读：

1. 本文件（AGENTS.md）— 项目指令与开发约定（强制：目录划分、常用命令、测试门禁、提交规范）
2. `CONTEXT.md` — 领域术语正名 / 违禁词（最高优先级，先读它再动手）
3. `docs/wayfinder/map.md` 与相关 `docs/adr/` — 决策追踪（计划是权威，不绕开它）
4. `docs/development-standards.md` — 编码/命名/类型/异常/日志规范（强制）
5. `docs/version-baseline.md` — 依赖钉版与实现门禁

任何与 AGENTS.md 冲突的本地约定均无效，以 AGENTS.md 为准。

---

证据优先（evidence-first）的医疗 RAG 知识工作台，用 Python 3.14 复刻 Java 参考项目 `D:\yzb\ragent`（**行为对齐，非代码拷贝**）。医疗安全边界：不生成无证据支持的个人临床决策。

## 设计上下文

- **Register:** product（聊天工作台 + 运营后台，设计服务于任务）；**Platform:** web（Vite SPA）。完整上下文见 `PRODUCT.md`。
- **设计系统：** `DESIGN.md`（规范）+ `apps/web/src/styles/tokens.css`（Tailwind v4 实现）。
- **品牌：** 可信·克制·清晰；单一 Notion 蓝功能色 + 暖纸壳 + 发丝边框无阴影；反参考：陈旧医院后台 / 通用 AI 聊天机器人 / 暗黑开发者工具。
- **设计原则：** ① 证据即界面（溯源/引用始终可达）② 克制即权威 ③ 临床级清晰（高对比、密度、固定刻度、安全边界最显眼）④ 状态性而非装饰（150–250ms、骨架屏、语义状态）⑤ 跨面一致性。
- **无障碍：** WCAG 2.2 AA（对比≥4.5:1、focus ring、键盘导航、状态不只靠颜色、reduced-motion）。

## 术语（强制）

所有标识符、注释、文档、UI 文案必须使用 `CONTEXT.md` 的正名，禁止 Avoid 词。**先读 `CONTEXT.md` 再动手。**

## 关键文档

| 文档 | 用途 |
|---|---|
| `CONTEXT.md` | 领域术语正名/违禁词（最高优先级）|
| `docs/development-standards.md` | 编码/注释/命名/类型/异常/异步/日志脱敏/包边界（强制）|
| `docs/version-baseline.md` | 依赖钉版清单 + 实现门禁 |
| `docs/spec.md` / `docs/architecture.md` | 规范与架构（与 ADR 一致）|
| `docs/wayfinder/map.md` | 决策追踪（所有已定决策索引）|
| `docs/adr/` | 架构决策记录 |
| `docs/reference/stack-replacement-matrix.md` + `behavior-parity-matrix.md` | ragent 迁移矩阵（parity 门禁）|
| `docs/research/implementation-recipes.md` | 各功能官方推荐实现配方 |

## 开发强制规则：使用 ponytail

**每次开发任务（写、改、修、重构、审代码）都必须运用 ponytail 原则**：只做最懒且正确的最小解（YAGNI）——优先标准库、优先原生能力、一行不写五十行、不加投机抽象、不造假想需求。违反它即是过度工程。

- 写/改/修代码时：调用 `ponytail` skill（`/ponytail`）作为懒人基准，检查"这个任务是否真的需要存在、这段能否用标准库/更简替代"。
- 审查 diff 时：对改动跑 `ponytail:ponytail-review`（只找过度工程/可删物）或 `ponytail:ponytail-audit`（全仓）作为质量关口。
- 与 `docs/development-standards.md` §0「最简正确（YAGNI）」一致；医疗安全/证据正确性是底线，不因追求简单而牺牲。

## 目录划分规范

单仓库 monorepo：一个 uv workspace（Python）+ 一个 pnpm workspace（JS/TS）+ Turborepo（仅 JS 任务）+ 根 `docker-compose.yml`。

```
MedicalRAG/
├── docker-compose.yml           # 唯一 Compose 入口（默认构建并启动全部服务；observability 为可选 profile）
├── pyproject.toml               # uv workspace root（requires-python >=3.14）
├── .python-version              # 3.14.x 锁定
├── package.json / pnpm-workspace.yaml / turbo.json   # 仅前端 JS 工具链
├── apps/                        # 可独立部署的应用（互不 import）
│   ├── api/                     #   FastAPI 组合根：认证/业务/管理 API、摄取触发（写 outbox）
│   ├── agent/                   #   Aegra + LangGraph 聊天管线（StateGraph、Thread/Run、v2 流式）
│   ├── worker/                  #   TaskIQ worker：摄取 job + outbox relay（9 阶段）
│   ├── evaluation/              #   隔离评测 runner（确定性检索指标 + 可选 RAGAS；不常驻生产）
│   └── web/                     #   Vite SPA（React 19 + TanStack Router/Query + assistant-ui）
├── packages/                    # 共享包
│   ├── medical-core/            #   领域 seam：实体/状态机/策略/端口/确定性服务（无框架依赖）
│   └── infra/                   #   具体适配器：PG/Redis/Qdrant/TaskIQ/对象存储/外部 provider/可观测
├── infra/                       # 部署资产（Dockerfile/Compose 初始化）——不是 Python 包
├── docs/                        # 本表所列文档 + ADR + research + wayfinder
└── scripts/                     # ci/ dev/ codegen（openapi → TS）
```

约定：
- `apps/*` 不互相 import；共享行为经 `medical-core` / `infra`。
- `medical-core` 不 import 任何框架（FastAPI/LangGraph/SQLAlchemy 等）；聊天图在 `apps/agent`。
- `packages/infra` 导入名 `medicalrag_infra`；禁止 `helpers.py`/`common.py` 垃圾桶。
- 新包必须通过 ADR 0060 的 deletion test（删掉它是否丢行为）才配拥有 seam。

## 常用命令

- Python：`uv sync --locked`、`uv run --package medicalrag-api <cmd>`
- 前端：`pnpm install --frozen-lockfile`、`pnpm turbo run lint typecheck test:unit build`
- Compose：`docker compose up -d`（默认构建并启动全部中间件与应用服务；自托管 Langfuse 加 `--profile observability`；集成测试中间件加 `--profile test`）
- 集成测试（ADR 0080）：`docker compose --profile test up -d postgres-test` 后 `MEDICALRAG_TEST_DATABASE_URL=postgresql+asyncpg://medicalrag_test:medicalrag_test@127.0.0.1:5433/medicalrag_test uv run pytest -m integration`（未设环境变量自动跳过）
- E2E（ADR 0080）：compose 全栈起来后 `pnpm --filter @medicalrag/web exec playwright install chromium && pnpm --filter @medicalrag/web test:e2e`
- 类型/覆盖率门禁：`uv run pyright`；`uv run pytest --cov`（fail_under=80，见根 pyproject）
- 契约（ADR 0071 单一来源）：导出 `uv run --package medicalrag-api python scripts/dev/export_openapi.py`，检查 `pnpm --filter @medicalrag/web contract-check`（openapi-typescript `--check` 漂移门禁）
- 评测：`uv run --package medicalrag-evaluation python -m medicalrag_evaluation.run eval-retrieval apps/evaluation/fixtures/retrieval.jsonl`
- 本机注意：Windows 上 `localhost`→`::1` 会挂起，本地 DB/Redis/代理 target 一律用 `127.0.0.1`（如 `MEDICALRAG_API_URL=http://127.0.0.1:8000`）

## 测试与验收（强制）

- **测试金字塔**：单元（medical-core 规则/状态机/策略，内存适配器，无外部服务）→ 契约（FastAPI OpenAPI、事件 envelope、Agent Protocol v2 对 Aegra、provider 适配器）→ 集成（Compose `test` profile：PG/Redis/Qdrant/TaskIQ+outbox）→ E2E（Playwright：登录/聊天流/来源/反馈/管理流）。
- **检索评测**：PR 跑 `eval-retrieval`（Recall@k、MRR/nDCG、intent Top-1、空召回率、P95）；RC 跑 `eval-answer`（RAGAS）。任何 RAGAS 分数都不能替代专家安全审核。
- **门禁**：提交级 = 格式/lint/typecheck/单元；PR 级 = + 契约测试 + `eval-retrieval` + 前端受影响包构建；合并/发布 = Compose 集成 + 迁移测试 + E2E + `eval-answer` + 镜像构建。contract-check = `pnpm --filter @medicalrag/web contract-check`。以上提交级与 PR 级门禁由 `.github/workflows/ci.yml` 机器强制（ADR 0080）；本地等价命令见上文。
- **UI 变更**：改前端必须在浏览器里实际跑通再宣称完成（见 `$impeccable` / `$verify` 流程），不能只靠 typecheck/单测。
- **parity 完成判据**：某能力只有在其迁移矩阵行（stack + behavior）有通过 fixture 才算 parity-complete（ADR 0049）。

## 变更流程

- 改代码前先查 `docs/wayfinder/map.md` 与相关 ADR——计划是权威，不绕开它。
- 任何新决策：先写 ADR（难逆/无上下文/真实权衡三条件），再更新 map Decisions-so-far，最后同步 spec/architecture；不反向改计划去迁就代码。

## GitHub 提交规范

- **格式**：`<type>(<scope>): <subject>`（Conventional Commits）。
- **type**：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci` / `build` / `style`。
- **scope**（monorepo 域）：`api` / `agent` / `worker` / `web` / `evaluation` / `medical-core` / `infra` / `compose` / `adr` / `docs` / `tooling`。
- **subject**：祈使句、小写开头、≤50 字符、不加句号。**Body 解释"为什么"**，决策相关可引用 ADR，例如 `refactor(medical-core): narrow seam to ports (ADR 0025)`。
- **破坏性变更**：subject 加 `!`（如 `feat(api)!: drop /v1/legacy`），footer 写 `BREAKING CHANGE: ...`。
- **术语**：commit message 用 CONTEXT.md 正名，不用 Avoid 词。
- **红线**：禁止把密钥、令牌、患者信息写进 commit 或 diff。
- **契约联动**：改动 FastAPI 路由/Pydantic 模型时，同一 commit 必须带上 openapi-typescript 生成产物，保持 contract-check 绿。

## 沟通

规划/决策讨论用中文；`CONTEXT.md`、ADR、spec 等持久文档可按其既有语言维护。决策变更先更新对应 ADR + map，再同步 spec/architecture（见 `docs/development-standards.md` 引用链）。
