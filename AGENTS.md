# AGENTS.md — MedicalRAG 项目说明与开发约定

本文件是本仓库唯一开发指令文件（原 `CLAUDE.md` 已并入并移除）。先读本文件，再动手。

开始任何写、改、修、重构、审代码工作前，按优先级阅读：

1. 本文件（AGENTS.md）— 项目指令与开发约定（强制：目录划分、常用命令、测试门禁、提交规范）
2. `CONTEXT.md` — 领域术语正名 / 违禁词（最高优先级，先读它再动手）
3. `docs/DECISIONS.md` 与 `docs/adr/` — 当前有效决策（不绕开已定决策）
4. `docs/development-standards.md` — 编码/命名/类型/异常/日志规范（强制）
5. `docs/version-baseline.md` — 依赖钉版与实现门禁

任何与 AGENTS.md 冲突的本地约定均无效，以 AGENTS.md 为准。

---

证据优先（evidence-first）的医疗 RAG 知识工作台，用 Python 3.12 复刻 Java 参考项目 `D:\yzb\ragent`（**行为对齐，非代码拷贝**）。医疗安全边界：不生成无证据支持的个人临床决策。

## 设计上下文

- **Register:** product（聊天工作台 + 运营后台，设计服务于任务）；**Platform:** web（Vite SPA）。
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
| `docs/testing-seams.md` | 测试接缝登记：新测试先对准接缝，含「明确不覆盖」与删除判据 |
| `docs/version-baseline.md` | 依赖钉版清单 + 实现门禁 |
| `docs/spec.md` / `docs/architecture.md` | 规范与架构（与 ADR 一致）|
| `docs/DECISIONS.md` | 当前有效决策一览 |
| `docs/adr/` | 架构决策记录（Accepted；索引见 `docs/adr/README.md`）|

## 开发强制规则：使用 ponytail

**每次开发任务（写、改、修、重构、审代码）都必须运用 ponytail 原则**：只做最懒且正确的最小解（YAGNI）——优先标准库、优先原生能力、一行不写五十行、不加投机抽象、不造假想需求。违反它即是过度工程。

- 写/改/修代码时：调用 `ponytail` skill（`/ponytail`）作为懒人基准，检查"这个任务是否真的需要存在、这段能否用标准库/更简替代"。
- 审查 diff 时：对改动跑 `ponytail:ponytail-review`（只找过度工程/可删物）或 `ponytail:ponytail-audit`（全仓）作为质量关口。
- 与 `docs/development-standards.md` §0「最简正确（YAGNI）」一致；医疗安全/证据正确性是底线，不因追求简单而牺牲。

## 目录划分规范

单仓库 monorepo：一个 uv workspace（Python）+ 一个 pnpm workspace（JS/TS）+ 根 `docker-compose.yml`。任务编排由两个生态各自的原生工具承担（uv / pnpm），不引入第三方编排器。

```
MedicalRAG/
├── docker-compose.yml           # 唯一 Compose 入口（默认构建并启动全部服务；observability 为可选 profile）
├── pyproject.toml               # uv workspace root（requires-python >=3.12）
├── .python-version              # 3.12.x 锁定
├── package.json / pnpm-workspace.yaml            # 仅前端 JS 工具链（任务编排用 pnpm 原生脚本）
├── apps/                        # 应用（可独立部署或独立运行；互不 import）
│   ├── api/                     #   FastAPI 组合根：认证/业务/管理 API、摄取触发（写 outbox）；唯一 migrations owner
│   ├── agent/                   #   Aegra + LangGraph 聊天管线（StateGraph、Thread/Run、v2 流式）
│   ├── worker/                  #   TaskIQ worker：摄取 job + outbox relay（9 阶段）
│   ├── evaluation/              #   隔离评测 runner（确定性检索指标 + 可选 RAGAS；不常驻生产）
│   └── web/                     #   Vite SPA；OpenAPI 生成物（schema.json / schema.d.ts）暂住此（单消费者例外）
├── packages/                    # 共享包
│   ├── medical-core/            #   领域 seam：实体/状态机/策略/端口/确定性服务（无框架依赖）
│   ├── infra/                   #   具体适配器：PG/Redis/Qdrant/对象存储/外部 provider/可观测
├── docs/                        # living docs + Accepted ADRs（规划期材料在 _archive/，不进 GitHub）
└── scripts/                     # ci/ dev（openapi 导出 → TS；包边界检查）
```

约定：
- `apps/*` 不互相 import；共享行为经 `medical-core` / `infra`。
- `medical-core` 不 import 任何框架（FastAPI/LangGraph/SQLAlchemy 等）；聊天图在 `apps/agent`；确定性 `ChatPipeline` 在 core。
- `packages/infra` 导入名 `medicalrag_infra`；禁止 `helpers.py`/`common.py` 垃圾桶；persistence 按领域模块聚合，`operator.py` 仅组合门面。
- 聊天流水线装配收敛于 `apps/agent`（ADR 0060 deletion test：API 下线 SSE 聊天后 assembly 仅剩单一消费者，包已解散）。
- Dockerfile 与所属 app 同目录（`apps/<app>/Dockerfile`，web 同规）；不存在仓库级 `infra/` 部署目录。
- 契约：无独立 `packages/contracts`；FastAPI OpenAPI 单向生成 TS 类型落在 `apps/web`（ADR 0071；第二 TS 消费者出现前不建包）。
- migrations 只在 `apps/api/migrations` 演进；agent/worker 只读 schema，不各自建表。
- 包边界：`uv run python scripts/ci/check_package_boundaries.py`（core↛infra/apps、apps 互独立）。
- pnpm workspace 成员仅 `apps/web`（`packages/*` 归 uv）；workspace 只用于成员发现与 `--filter`，任务编排走 pnpm 原生脚本（无第三方编排器）。JS 共享代码在出现第二个消费者前并入 `apps/web`；禁止放进 `packages/`（uv 会静默忽略无 pyproject.toml 的目录）。
- 新包必须通过 ADR 0060 的 deletion test（删掉它是否丢行为）才配拥有 seam。
- 本地对象根 `objects/` 运行时创建且 gitignore；`_archive/` 为本地文档归档，禁止提交。

## 常用命令

- Python：`uv sync --locked --all-packages`、`uv run --package medicalrag-api <cmd>`
- 前端：`pnpm install --frozen-lockfile`、`pnpm --filter @medicalrag/web run check`（lint/typecheck/test:unit/build/fmt:check 单命令门禁）
- Compose：`docker compose up -d`（默认构建并启动全部中间件与应用服务；自托管 Langfuse 加 `--profile observability`；集成测试中间件加 `--profile test`）
- 集成测试（ADR 0080）：`docker compose --profile test up -d postgres-test` 后 `MEDICALRAG_TEST_DATABASE_URL=postgresql+asyncpg://medicalrag_test:medicalrag_test@127.0.0.1:5433/medicalrag_test uv run pytest -m integration`（未设环境变量自动跳过）
- E2E（ADR 0080）：compose 全栈起来后 `pnpm --filter @medicalrag/web exec playwright install chromium && pnpm --filter @medicalrag/web test:e2e`
- 类型/覆盖率门禁：`uv run pyright`；`uv run pytest --cov`（总量地板 `fail_under=75`，口径为**行 + 分支**，见根 pyproject）；变更行门禁 `uv run python scripts/ci/check_patch_coverage.py --base origin/main`（ADR 0088）；门禁自身回归 `uv run pytest scripts/ci/tests`
- 包边界：`uv run python scripts/ci/check_package_boundaries.py`
- 契约（ADR 0071 单一来源）：导出 `uv run --package medicalrag-api python scripts/dev/export_openapi.py`，检查 `pnpm --filter @medicalrag/web contract-check`（openapi-typescript `--check` 漂移门禁）
- 评测：`uv run --package medicalrag-evaluation python -m medicalrag_evaluation.run eval-retrieval apps/evaluation/fixtures/retrieval.jsonl`（指标跌破内定下限即非零退出；该步不跑真实检索器，边界见下）
- 本机注意：Windows 上 `localhost`→`::1` 会挂起，本地 DB/Redis/代理 target 一律用 `127.0.0.1`（如 `MEDICALRAG_API_URL=http://127.0.0.1:8000`）

## 测试与验收（强制）

- **测试金字塔**：单元（medical-core 规则/状态机/策略，内存适配器，无外部服务）→ 契约（FastAPI OpenAPI、事件 envelope、Agent Protocol v2 对 Aegra、provider 适配器）→ 集成（Compose `test` profile：PG/Redis/Qdrant/TaskIQ+outbox）→ E2E（Playwright：登录/聊天流/来源/反馈/管理流）。
- **检索评测**：PR 跑 `eval-retrieval`（Recall@k、MRR/nDCG、Top-1 命中、空召回率、P95）并带指标下限判决（跌破即红）；RC 跑 `eval-answer`（RAGAS）。**边界**：`eval-retrieval` 的候选集来自固定 fixtures，不执行真实检索器——它挡的是指标实现与 fixtures 的回归，不是检索器回归（真实检索路径当前无集成载体，见 `docs/testing-seams.md`）。任何 RAGAS 分数都不能替代专家安全审核。
- **门禁**：提交级 = 格式/lint/typecheck/单元 + 包边界 + schema 漂移（`alembic check`）；PR 级 = + 变更行覆盖率门禁（patch coverage，ADR 0088）+ 契约测试 + `eval-retrieval`（含下限）+ 四镜像构建 + 前端 fmt:check 与受影响包构建；合并/发布 = Compose 集成 + 迁移测试 + E2E + `eval-answer`。contract-check = `pnpm --filter @medicalrag/web contract-check`。机器载体现状：提交级/PR 级由 `.github/workflows/ci.yml` 强制；**合并后**（postsubmit，`push: main`）由 `.github/workflows/integration.yml` 强制（真 PostgreSQL 全量 + 不许 skip 守卫）——它**不是** PR 阻断门；E2E 与 `eval-answer` 目前**无 CI 载体**，属本地/发布流程（接入 CI 的前提是先本地连续稳定通过，见 `docs/testing-seams.md`）。本地等价命令见上文。
- **UI 变更**：改前端必须在浏览器里实际跑通再宣称完成（见 `$impeccable` / `$verify` 流程），不能只靠 typecheck/单测。
- **接缝**：新测试先对准 `docs/testing-seams.md` 登记的接缝；测试只写在公共边界上，不对着内部实现写。
- **parity 完成判据**：某能力只有在其迁移矩阵行（stack + behavior）有通过 fixture 才算 parity-complete（ADR 0049）。

## 变更流程

- 改代码前先查 `docs/DECISIONS.md` 与相关 Accepted ADR——已定决策是权威，不绕开它。
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
