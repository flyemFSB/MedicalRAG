# 高质量 Python 代码标准/规范调研（适配 MedicalRAG）

> Generated 2026-09-15 · depth: deep · 81 sources · workspace: research/python-standards/

## Executive summary

- **语言层已无“风格战争”**：PEP 8/257/484 + Python 3.12 typing 文档仍是唯一权威基线；生产代码应显式标注公共 API（含 `-> None`），优先 `type Alias = ...`、`X | Y`、`Self`/`Never`/`LiteralString`，端口用紧凑 `Protocol`，JSON 固定键用 `TypedDict`，领域对象用 dataclass/Pydantic [1][2][3][4][5][6]。MedicalRAG 的 `docs/development-standards.md` 已覆盖命名/异常/docstring 主线，与外部标准一致。
- **工具链收敛为三件套**：ruff（lint+format）+ 类型检查器（mypy/pyright）+ uv lockfile；官方推荐显式 `select = ["E","F","UP","B","SIM","I"]` 而非 `ALL`，且 ruff **不能**单独替代类型检查 [11][12][15][16]。本仓 ruff 配置已含该集合，并额外打开 `ASYNC`/`RUF`——与医疗异步栈匹配，优于“最小集合”默认值。
- **异步是本仓最大隐性风险面**：官方要求 `TaskGroup`/`asyncio.timeout` 取代裸 `gather`/`wait_for`；禁止吞 `CancelledError`；`create_task` 只持弱引用；SQLAlchemy 2 禁止并发共用 `AsyncSession` 与隐式 lazy IO；FastAPI yield 依赖默认在响应后清理，吞异常会“客户端 500、服务端无日志” [26][27][28][29]。ruff `ASYNC` 规则正是这些生产事故的机器化编码 [31]。
- **RAG 工程规范已可操作**：LangGraph 生产必须用持久 checkpointer（非 InMemory），HITL/`interrupt()` 会重跑节点故副作用须幂等 [33][34]；评测从“凭感觉”升级为 RAGAS 指标套件（检索与生成分测）[36][37][38][39]；prompt/检索上下文应版本化并与代码分离 [41]。OWASP LLM Top 10（2026）给出 Excessive Agency / Overreliance / Prompt Injection 等护栏边界 [43]。
- **日志红线有外部背书**：OWASP 明确禁止落盘健康/PII、token、连接串、密钥，要求 when/where/who/what 与防注入清洗；**不要**记完整 prompt / MCP tool I/O，只记规则 ID 与 request 标识 [45][46]。loguru 官方 recipe 要求生产 `diagnose=False`、防 format-string 注入、日志文件 `0o600` [47]。本仓 `SAFE_FIELDS` 白名单方向正确，可补上 diagnose 与文件权限两项。
- **包边界需要机器门禁，不能只靠约定**：Cockburn/Martin 一致要求依赖只向内、违规可自动检出 [66][67]；uv workspace **明确无法**阻止跨成员 import（“Python does not provide dependency isolation”）[17]。业界标准工具是 Import Linter v2.15（layers / independence / acyclic_siblings / forbidden）[68][69][70]——本仓自有 `check_package_boundaries.py` 功能相近，可并存或迁移到契约配置。
- **测试门禁：总量 + 变更行 + 分支**：官方/工具文档支持 pyramid 形状 [55]、branch coverage 捕获语句覆盖漏掉的分支 [57][58]、diff-cover 守“碰过的行必须测到”[59]；pytest 9 新项目可用 `strict = true` 一键收紧 [61]。本仓 `fail_under=75`（行+分支）+ patch coverage 已属先进配置。
- **医疗过程标准（非认证）**：FDA CDS 2026 终稿 + FAQs 将“时间关键决策”“只给单一临床建议”排除出 Non-Device CDS [75][76]；ONC HTI-1 对 Predictive DSI 要求按八特征做干预风险管理（validity/reliability/robustness/fairness/intelligibility/safety/security/privacy）[78]。它们可映射为 eval 与文档 rubric，**不**等于本产品要走 SaMD 注册。
- **整体判断**：MedicalRAG 现有规范与外部高质量标准**高度重合**，且在医疗安全/术语/包边界上更严。真正值得吸收的是**可机器执行的增量**（Import Linter 契约、loguru diagnose、pytest strict、依赖审计、pyright 收紧路径）与 **ONC 八特征评测 rubric**，而不是重写规范。

## Background & scope

本调研回答：哪些业界公认的高质量 Python 标准/规范最适配 MedicalRAG（证据优先医疗 RAG monorepo，Python 3.12 + uv + FastAPI + LangGraph + Qdrant），以及相对已有 `docs/development-standards.md` / ADR / version-baseline 如何对齐、补强或纠偏。

**边界**：只谈 Python 侧；不评前端；不改代码；不宣称任何监管认证。假设读者已读 CONTEXT.md 与 AGENTS.md 的 ponytail/YAGNI 约定。时间窗以 2026-09 可访问的一手文档为主。

---

## 1. 语言与类型（PEP / typing）

### 1.1 基线

PEP 484 明确：运行时**不做**类型检查，注解服务离线静态检查器；被检查函数默认未标注槽位是 `Any`，因此公共 API 应标全参数与返回类型，`__init__ -> None` [1]。Python 3.12 起官方 typing 文档指向 living 规范（typing.python.org），并推荐 PEP 695 语法：`type Alias = ...` 取代 `TypeAlias`，泛型用 `def f[T]` / `class C[T]`，方差由使用推断 [2][3][4]。

### 1.2 结构类型与数据载体怎么选

| 场景 | 标准选择 | 理由 |
|---|---|---|
| 端口/适配器依赖倒置 | 紧凑 `Protocol`（可选 `@runtime_checkable`） | 结构子类型，与 ABC 互补而非取代 [5] |
| 固定键 JSON 载荷 | `TypedDict` | 运行时是普通 `dict`，无方法、无 `isinstance` [6] |
| 领域值对象/DTO | `dataclass`（必要时 `frozen=True`/`slots=True`）或 Pydantic model | dataclass 直接服务对象语义；Pydantic 适合边界校验 [7] |
| 异常 | 自定义继承 `Exception`，`Error` 后缀，`raise X from Y` | PEP 8 与 3.12 exceptions 文档一致 [8][9] |

### 1.3 Docstring

PEP 257 要求模块/公共类/函数/方法（含 `__init__`）有 docstring，并覆盖行为、参数、返回、副作用、异常 [10]。生产二次源 Google Style 使用结构化 Args/Returns/Raises，强制公共 API 类型注解，禁止裸 `except:` [10]。本仓要求“解释为什么 + 不变量/失败语义”，比纯 Google 模板更贴近医疗端口，应保留。

### 1.4 对本仓的映射

- 与现有 §1.1–1.3 **一致**；可把 3.12 `type` 语句与 `X | Y` 写进命名/类型小节作为唯一允许写法，避免 `Optional`/`Union`/`TypeAlias` 回潮。
- `medical-core` 端口用 Protocol 而非 ABC，是 PEP 544 推荐的紧凑写法；事件 envelope 已是 Pydantic，保持边界校验在 adapter/API 层，领域层不必强上 Pydantic。

---

## 2. 工具链门禁（ruff / 类型检查 / uv）

### 2.1 Ruff：显式 select，禁止 ALL

Astral 官方：优先 `select` 而非 `extend-select`；`ALL` 会在升级时隐式吸入新规则；示例生产集合为 `E,F,UP,B,SIM,I` [12]。默认规则本身是高信号子集（含部分 UP/B/ASYNC/RUF），但多数纯风格 E 规则默认关闭 [13]。Formatter 与 Black 高度一致，目标不是创新风格 [14]；import 排序在 format **之外**：`ruff check --select I --fix && ruff format` [14]。

**对本仓**：根 `pyproject.toml` 的 `select = E,F,UP,B,SIM,I,ASYNC,RUF` **优于**官方最小示例，因为 ASYNC 直接覆盖事件循环阻塞 I/O 等生产 bug [31]。应写明：不引入 `ALL`；若加规则组（如 `TRY`/`PERF`/`PTH`）按组评估，避免格式器冲突规则（W191、COM812 等）[14]。

### 2.2 类型检查：Ruff 不够，必须配检查器

Ruff FAQ 明确其不是 Pylint 的纯替代，推荐与 mypy/pyright/pyre 组合 [15]。mypy 文档把 `--strict` 作为生产目标，并给出等价 flag 列表；`strict_optional = false` 被点名 “evil” [16]。大规模代码库应对子集起步、钉版本、尽快进 CI [16]。

**对本仓**：pyright `basic` 起步（ADR 0080）符合“先落地再收紧”。建议在 development-standards 写一条**收紧轨迹**：core 关键路径 → 启用更严 report\* → 评估是否对 core 近 strict；勿同时双开 mypy 与 pyright。

### 2.3 uv / src-layout / lock

- workspace：单 lockfile、单 `requires-python` 交集；成员用 `tool.uv.sources` workspace 依赖 [17]。
- CI：`uv sync --locked`（lock 过期则失败）优于静默更新；官方 GHA 示例钉 `setup-uv` 版本 [18][19]。
- `uv.lock` 必须提交；`uv lock --check` 只校验不重写 [20]。
- src-layout 是 PyPA 正式推荐：强制安装、防止 cwd 误 import 开发树 [21][61]。

**对本仓**：与 version-baseline / AGENTS 命令完全对齐。可补 pre-commit 钩子 `uv-lock` 作 DX，CI 仍是权威 [23]。

### 2.4 观察项（非建议立刻切换）

Astral `ty` 宣称比 mypy/pyright 快 10–100×，有迁移文档，但成熟度仍只适合观察，不适合作为本仓门禁 [22]。

---

## 3. 异步正确性

这是外部标准与本仓“强制规则”重合度最高、也最值钱的一章。

### 3.1 取消与结构化并发

- AnyIO/Trio 为 level-triggered：取消范围内每个 yield 都会再取消；asyncio 为 edge-triggered，超时后的 cleanup await 可能永久挂起 [24][25]。
- 必须重新抛出取消异常；cleanup 里若需 await，用 `CancelScope(shield=True)` [24]。
- `asyncio.create_task` 只持弱引用，fire-and-forget 可能中途被 GC；用 `TaskGroup` 或持有 set 强引用 [26]。
- `TaskGroup` 首个非 CancelledError 失败会取消兄弟任务并抛 `ExceptionGroup`；裸 `gather` 不会 [26]。
- 不要吞 `CancelledError`——会破坏 TaskGroup/timeout 内部机制 [26]。

### 3.2 SQLAlchemy 2 async

- 单个 `AsyncSession` **不可**被并发任务共用；一任务一 session [27]。
- 禁止隐式 IO（lazy load、过期属性访问）；用 `selectinload`/`joinedload`/`awaitable_attrs`/`run_sync` [27]。

### 3.3 FastAPI

- yield 依赖默认在**响应之后**清理（`scope="request"`）；需要响应前关闭用 `Depends(scope="function")` [28]。
- yield 依赖里 catch 后不 re-raise：客户端仍是 500，但**服务端无日志** [28]。
- 启动/关闭用 `lifespan=`，`on_event` 已废弃且互斥 [29]。
- BackgroundTasks 在同进程响应后跑；重活/多进程走队列（本仓 TaskIQ/outbox 路径正确）[30]。

### 3.4 对本仓的可执行增量

1. 开发规范把“禁止吞 CancelledError”“一 task 一 AsyncSession”“yield 依赖必须 re-raise”升为与“禁事件循环阻塞 I/O”同级的红线。
2. 代码审阅清单：`create_task` 是否有强引用或 TaskGroup；worker/agent 清理路径是否 shield。
3. ruff `ASYNC` 已在 select 中——保持；新模块 PR 必须过 ASYNC 零违规。

---

## 4. AI / LLM / RAG 工程规范

### 4.1 LangGraph 生产形态

LangGraph 定位是低层编排运行时，允许确定性步与 LLM 步混在同一图 [32]。生产：

- 持久 checkpointer（如 PostgresSaver）；InMemorySaver 进程重启即丢 [33]。
- 短期 thread 记忆 vs 长期 store 分离 [33]。
- HITL `interrupt()` 会**整节点重跑**，interrupt 前副作用必须幂等；不要 bare try/except 包住 interrupt [34]。
- 节点可重入：插库不能靠“跑两次就会重复”赌运气 [35]。

**对本仓**：与 Aegra + LangGraph + Postgres checkpoint 基线一致；ingestion outbox/幂等已在 ADR 体系内。建议把“节点幂等 + interrupt 重跑”写进 agent 侧端口 docstring 不变量（development-standards §1.2 已要求，可点名此场景）。

### 4.2 评测：从 vibe 到指标

RAGAS 官方把评测定位为系统化 loop，而非一次性人工感觉 [36]。与本仓相关：

- **Faithfulness** = 响应中被检索上下文支持的 claim 数 / 总 claim 数 [37]。
- **Context Recall** 衡量检索完整度；有 LLM / Non-LLM / ID-based 变体 [38]。
- 指标套件区分检索质量（Context Precision/Recall、Noise Sensitivity 等）与生成质量（Faithfulness、Response Relevancy），agent 另有 tool/goal 指标 [39]。

**对本仓**：`eval-retrieval`（确定性）+ `eval-answer`（RAGAS，隔离解释器）结构正确。RAGAS 分数**不能**替代专家安全审核——与外部“系统化评测”并不冲突，医疗边界更严。

### 4.3 Prompt / 可观测 / 护栏

- Traces 是生产行为记录，用于 debug、监控、构建评测集；prompt/检索上下文应版本化、可环境晋升 [40][41]。
- 结构化输出：Tool（默认）/ Native / Prompted 三模式，Pydantic 校验 + ModelRetry [42]。
- OWASP LLM Top 10（2026）：Prompt Injection、Insecure Output Handling、Excessive Agency、Overreliance 等为护栏边界 [43]。

**对本仓（重要纠偏）**：外部“上 LangSmith / OTel GenAI”与 **ADR 0062/0074 已明确相反**——不铺自定义 Trace，日志 loguru + 指标 Prometheus，Langfuse 仅脱敏元数据且 fail-open。**保持 ADR，不因外部流行栈回潮。** 可吸收的是 OWASP 边界清单与 prompt 版本化意识，不是换观测产品。

---

## 5. 安全、隐私与日志红线

### 5.1 日志

OWASP Logging Cheat Sheet：

- 禁止直接记录 PII/健康数据、session id、token、密码、连接串、密钥——应删除/掩码/哈希/加密 [45]。
- 健康数据、政府标识、弱势人群数据属最高敏 [45]。
- 每条日志 when/where/who/what；扩展细节（HTTP body、stack）分文件/表 [45]。
- 清洗 CR/LF/分隔符防 log injection；跨信任域数据当不可信 [45]。
- Vocabulary 补充：ISO 8601 带偏移；**不要**记 SQLi payload、完整 prompt/tool I/O、CSP 报文——记规则 ID、参数名、request 标识 [46]。

Loguru recipe（生产）：

- `diagnose=False`（默认 True 会在异常里 dump 变量，可能泄露凭据）[47]。
- 转义用户可控 format string，防 `{value.__init__.__globals__[SECRET_KEY]}` 类攻击 [47]。
- 日志文件 `0o600` [47]。

**对本仓**：`SAFE_FIELDS` 白名单 + “永不写 raw prompt/evidence/患者标识/凭据”与 OWASP 同向且更具体。建议立刻核对三项增量：生产 sink `diagnose=False`（或 `LOGURU_DIAGNOSE=NO`）、format 硬化、文件权限。

### 5.2 密钥与依赖

- OWASP Secrets：集中存储、最小权限、自动轮换、禁止明文传输、审计请求/使用/轮换 [50]。
- pip-audit（PyPA，2026-06 v2.10.1）：OSV/PyPI advisory，exit 1 不可抑制；支持 `--locked` 与 CycloneDX SBOM [51]。
- uv malware-check（preview）：sync 时扫 lockfile 对 OSV MAL；`uv export --format cyclonedx1.5` [18]。
- Bandit：硬编码密钥、弱权限、弱加密、shell 注入，以及 ML 载入相关 B614/B615 [52][53]。
- OWASP 依赖漏洞管理：从项目出生就自动化分析；silence scanner 或改版本号**不是**修复 [54]。

**对本仓**：secrets 走启动 fail-fast + 生产 secrets 已有约定。建议把 `pip-audit --locked`（或 uv malware-check）与可选 Bandit 放进 PR/定期安全 job——这是目前外部标准相对本仓最大的**工具缺口**。

### 5.3 法规映射（工程控制，非认证声明）

- HIPAA 45 CFR 164.312 技术保障：访问控制、审计控制、完整性、认证、传输安全；相关文档保留至创建/生效后 6 年 [48][49]。
- GDPR Art. 25：设计默认的数据最小化与假名化 [49]。

本仓若仅处理用户上传知识库而不存 ePHI，不必声称 HIPAA 覆盖；但日志最小化、访问审计、传输安全三原则与现有红线同构，可作 checklist。

---

## 6. 测试与质量门禁

### 6.1 形状与分层

Pyramid：大量快单元、适量集成、极少 E2E；窄集成一次打一个本地边界，不打生产 [55]。契约测试 = 双方各自对照共享契约（Pact “contract by example”）；**仅有** OpenAPI schema 检查不能证明消费者调用正确 [56][56]。

**对本仓**：Pyramid + OpenAPI drift + `docs/testing-seams.md` 接缝思想正确。与 Pact 差距是可接受的：单仓单消费者（web）时 OpenAPI `--check` 足够；第二消费者出现再引入 CDC [single source of decision in ADR 0071 spirit]。

### 6.2 覆盖率

- branch 模式捕获“语句盖满但分支未走”的缺口 [57][58]。
- `[report] fail_under` 低于目标 exit 2 [58]。
- diff-cover：变更行覆盖率，`--fail-under` 守 PR [59]。

本仓：总量 75（行+分支）+ patch coverage（ADR 0088）**已是文档级推荐组合**。可写清：diff-cover 是行口径，总量是行+分支口径，两者目的不同，不要混用阈值。

### 6.3 pytest 实践

- fixture 默认 function scope；yield fixture 每个只做一件改状态的事 + teardown [60]。
- pytest 9 `strict = true` 一键 strict_config/markers/parametrization_ids/xfail [61]。
- 新项目推荐 src-layout + `--import-mode=importlib` [61]。
- pytest-asyncio 是 asyncio 测试标准插件；本仓已 `asyncio_mode = auto` [63]。
- Hypothesis 是属性测试标准；mutmut 是变异测试（需 fork，Windows 需 WSL）[64][65]。

**增量建议（按 ponytail 收敛）**：

1. 在 pytest 配置评估 `strict = true`（覆盖现有 `--strict-markers` 并再收紧）。
2. **不要**立刻上 mutmut/Hypothesis 作为门禁——医疗安全路径的状态机/策略可对 `medical-core` 局部试点 Hypothesis；mutmut 成本高，仅作可选。
3. 测试命名已要求 `test_<behavior>_<condition>_<expected>`，保持。

---

## 7. 架构与包边界

### 7.1 原则

Cockburn：内层代码不得泄漏到外层；无自动检测则分层承诺会腐化 [66][67]。Martin：依赖只能向内；跨边界用依赖倒置，禁止把 ORM row 传进领域 [67][67]。Cosmic Python：局部耦合在高内聚时是好事，无内聚的全局耦合超线性腐化成 Ball of Mud；禁止 config/helpers 垃圾桶 [71][72]。

### 7.2 机器门禁

- Import Linter v2.15（2026-09-04，Production/Stable）支持 `forbidden` / `protected` / `layers` / `independence` / `acyclic_siblings` [68]。
- `layers` 抓**间接** import（经 utils 中转也算）[69]。
- `acyclic_siblings` 抓包-子包环，纯 module-cycle 查不出 [70]。
- uv workspace **不能**保证成员不 import 其他成员的依赖——这是 Python 语言限制 [17]。

**对本仓**：`scripts/ci/check_package_boundaries.py` 已在做类似工作（core↛infra/apps、apps 互独立）。二选一（YAGNI）：

- **A（推荐短期）**：保持自有检查器，把 Import Linter 的 `acyclic_siblings`/`layers` 语义对照补进检查器测试；
- **B（若要社区可迁移性）**：用 import-linter 契约文件替换自有脚本，CI 仍一条命令。

不要两套长期并存。

### 7.3 布局

Cosmic Python：`domain / adapters / entrypoints / service_layer` + tests 分 unit/integration/e2e [72]。本仓 monorepo 按 app 分包 + medical-core 无框架依赖，本质是同一内核，不需要为贴书而改目录。

---

## 8. 医疗软件过程标准（非认证映射）

本产品定位 Evidence Answer，不是 Clinical Decision。外部监管语言可作**质量 rubric**，不作合规宣称。

| 外部要求 | 对 MedicalRAG 的工程含义 |
|---|---|
| FDA Non-Device CDS：时间关键决策排除 [76] | 产品文案与 Safety Boundary 明确不支持急救/时效决策场景 |
| FDA：只给单一临床建议失败 Criterion 3 [76] | 答案面避免“唯一方案”表述；保留多 Evidence / 局限说明 |
| 平台 vs 器械：SaaS 访问器械软件可能被视为制造商 [76] | 营销与交付形态决定监管面——工程侧保持可审计 |
| ONC HTI-1 IRM 八特征 [78] | 可映射到 eval/文档：validity↔eval-retrieval/answer；reliability↔确定性管线；robustness↔失败注入；fairness/intelligibility↔（缺口）；safety↔Safety Boundary；security/privacy↔日志与鉴权 |
| GMLP 10 原则（IMDRF 2025）[79] | 数据版本、独立评测、人机协同——与现有 eval/人工审核路径对齐 |
| 预注册软件文档清单（软件描述、架构、风险、V&V、未决缺陷）[80] | 已有 architecture/spec/ADR/testing-seams/eval 可拼成同等证据包 |

ISO/IEC 62304、ISO 14971、ISO/IEC 27001 条文本次未能取得一手全文（ISO.org 403），不在此臆造条款；若未来要体系化，再单独做条款级映射。

---

## 9. 与 MedicalRAG 现有规范对照

### 9.1 已对齐（保持，勿回退）

| 主题 | 外部标准 | 本仓 |
|---|---|---|
| ruff 显式 select + 非 ALL | [12] | 根 pyproject select 含 E,F,UP,B,SIM,I,ASYNC,RUF |
| src-layout | [21][61] | 全 workspace src |
| uv lock + `--locked` | [18][20] | version-baseline + CI |
| 禁事件循环阻塞 I/O | [31] | development-standards §1.4 + ASYNC |
| medical-core 无框架 | [67] | ADR 0025/0060 + 边界检查 |
| 禁 helpers/common 垃圾桶 | [72] | AGENTS / development-standards §4 |
| 日志禁 prompt/患者/凭据 | [45][46] | §3 红线 + SAFE_FIELDS |
| 测试金字塔 + 接缝 | [55] | AGENTS 测试章节 + testing-seams.md |
| 变更行覆盖率 | [59] | ADR 0088 patch coverage |
| 不铺自定义 OTel | 与流行栈相反的 ADR 0062 | 有意选择，保持 |

### 9.2 建议吸收的增量（按性价比排序）

1. **loguru 生产 recipe**：`diagnose=False`、format 硬化、日志 `0o600` [47] — 改动小、防泄露大。
2. **pytest `strict = true`**（或等价全套）[61] — 收紧现有 markers 门禁。
3. **依赖安全扫描**：`pip-audit --locked` 与/或 uv `malware-check` 定期 job [51][18]。
4. **异步红线补句**：吞 CancelledError、共用 AsyncSession、yield 依赖不 re-raise [26][27][28]。
5. **ONC 八特征 rubric**：给 eval-answer/testing-seams 增加 fairness/intelligibility 占位（即使暂标“未覆盖”）[78]。
6. **Import Linter 语义对齐**：决定 A 或 B（见 §7.2），避免双轨。
7. **类型收紧轨迹**：写清 pyright basic → 更严的触发条件（非立刻 strict）[16]。
8. **3.12 语法唯一化**：`type` 语句、`X | Y`、Protocol 端口写法落入 standards 附录 [2][4][5]。

### 9.3 明确不建议采纳

- 为贴外部“标准”把 loguru 换成 OTel 全家桶（违 ADR 0062/0074）。
- 引入 Pact/变异测试/属性测试作为**默认门禁**（成本与 YAGNI 不匹配；局部试点另说）。
- 按 Cosmic Python 强行改 monorepo 目录名。
- 以 RAGAS 分数或任何外部框架替代专家安全审核。

---

## Comparison table（可选标准 vs 本仓现状）

| 标准/工具 | 解决什么 | 本仓现状 | 建议 |
|---|---|---|---|
| PEP 8/257/484 + 3.12 typing | 风格与类型基线 | 已覆盖并加码 | 附录写 3.12 唯一语法 |
| ruff 显式 select + ASYNC | lint/format/异步反模式 | 已启用且更全 | 保持，禁 ALL |
| pyright/mypy strict 轨迹 | 类型安全 | basic | 写收紧轨迹 |
| uv --locked + src-layout | 可复现构建 | 已是 | 保持 |
| Import Linter | 包边界机器合同 | 自有脚本 | 对齐语义或迁契约 |
| OWASP Logging + loguru recipe | 防泄露/注入 | 白名单已有 | 补 diagnose/权限 |
| pip-audit / Bandit / uv malware | 依赖与 SAST | 缺口 | 加定期 job |
| RAGAS + 确定性 retrieval eval | 质量量化 | 已有双轨 | 保持；RAGAS≠安全审核 |
| LangGraph persistence/idempotency | 生产 agent | 对齐 | 文档点名 interrupt 重跑 |
| ONC HTI-1 八特征 | 预测型 DSI 风险 | 部分覆盖 | 映射 rubric |
| FDA CDS Non-Device | 产品边界 | Safety Boundary 思想对齐 | 场景文案固化 |
| IEC 62304 / ISO 14971 | 器械生命周期 | 未体系化 | 仅当升级监管目标时再调研 |

---

## Open questions

1. **Pyright 官方 configuration.md** 本轮 404/传输失败，`basic`→更严的具体 report\* 开关清单需在可达时补一次核对 [F2 dead ends]。
2. **IEC 62304:2006+A1:2015 / ISO 14971:2019** 一手条文未取得；若 MedicalRAG 未来声明器械相关，需条款级映射，不能用本报告 FDA/ONC 摘要代替。
3. **OTel GenAI semantic conventions** 与 **OpenAI structured outputs / Anthropic citations** 因 403/区域限制未取证；在 ADR 不铺 OTel 的前提下，优先级低。
4. **NumPy vs Google docstring** 未双取原文；本仓若统一 Google 风格即可，无需并列。
5. **Import Linter vs 自有边界检查器** 的迁移成本（脚本行数、CI 时长、自定义规则表达力）需在决策时实测，本报告只给语义对照。
6. 本轮多个子代理报告 **WebSearch 不可用**，全部改为已知一手 URL 直取；覆盖面已够 deep 预算，但可能漏掉只靠搜索发现的长尾实践文。

---

## Sources

访问日期均为 2026-09-15。

[1] PEP 484 – Type Hints — https://peps.python.org/pep-0484/  
[2] typing — Python 3.12 docs — https://docs.python.org/3.12/library/typing.html  
[3] PEP 695 – Type Parameter Syntax — https://peps.python.org/pep-0695/  
[4] PEP 544 – Protocols — https://peps.python.org/pep-0544/  
[5] PEP 544 (complementary to nominal subtyping) — https://peps.python.org/pep-0544/  
[6] PEP 589 – TypedDict — https://peps.python.org/pep-0589/  
[7] dataclasses — Python 3.12 docs — https://docs.python.org/3.12/library/dataclasses.html  
[8] PEP 8 – Style Guide — https://peps.python.org/pep-0008/  
[9] Built-in Exceptions — Python 3.12 docs — https://docs.python.org/3.12/library/exceptions.html  
[10] PEP 257 – Docstring Conventions — https://peps.python.org/pep-0257/  
[11] Google Python Style Guide — https://google.github.io/styleguide/pyguide.html  
[12] Ruff Linter (explicit select) — https://docs.astral.sh/ruff/linter/  
[13] Ruff default rules — https://docs.astral.sh/ruff/default-rules/  
[14] Ruff Formatter — https://docs.astral.sh/ruff/formatter/  
[15] Ruff FAQ (pair with type checker) — https://docs.astral.sh/ruff/faq/  
[16] mypy – Existing codebases / strict — https://mypy.readthedocs.io/en/stable/existing_code.html  
[17] uv Workspaces — https://docs.astral.sh/uv/concepts/projects/workspaces/  
[18] uv Sync / malware-check — https://docs.astral.sh/uv/concepts/projects/sync/  
[19] uv GitHub integration — https://docs.astral.sh/uv/guides/integration/github/  
[20] uv Project layout / uv.lock — https://docs.astral.sh/uv/concepts/projects/layout/  
[21] PyPA src-layout vs flat — https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/  
[22] Astral ty — https://docs.astral.sh/ty/  
[23] uv pre-commit — https://docs.astral.sh/uv/guides/integration/pre-commit/  
[24] AnyIO Cancellation — https://anyio.readthedocs.io/en/stable/cancellation.html  
[25] Trio core reference — https://trio.readthedocs.io/en/stable/reference-core.html  
[26] asyncio — Tasks / TaskGroup / timeout — https://docs.python.org/3/library/asyncio-task.html  
[27] SQLAlchemy 2 asyncio extension — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html  
[28] FastAPI Dependencies with yield — https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/  
[29] FastAPI Events / lifespan — https://fastapi.tiangolo.com/advanced/events/  
[30] FastAPI Background Tasks — https://fastapi.tiangolo.com/tutorial/background-tasks/  
[31] Ruff rules (incl. ASYNC) — https://docs.astral.sh/ruff/rules/  
[32] LangGraph Overview — https://docs.langchain.com/oss/python/langgraph/overview  
[33] LangGraph Persistence — https://docs.langchain.com/oss/python/langgraph/persistence  
[34] LangGraph Interrupts — https://docs.langchain.com/oss/python/langgraph/interrupts  
[35] LangGraph Graph API — https://docs.langchain.com/oss/python/langgraph/graph-api  
[36] RAGAS docs — https://docs.ragas.io/en/stable/  
[37] RAGAS Faithfulness — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/  
[38] RAGAS Context Recall — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/  
[39] RAGAS Metrics index — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/  
[40] LangSmith Observability — https://docs.langchain.com/langsmith/observability  
[41] LangSmith Prompt engineering — https://docs.langchain.com/langsmith/prompt-engineering  
[42] Pydantic AI Output — https://ai.pydantic.dev/output/  
[43] OWASP Top 10 for LLM Applications — https://owasp.org/www-project-top-10-for-large-language-model-applications/  
[44] Guardrails AI docs — https://docs.guardrailsai.com/  
[45] OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html  
[46] OWASP Logging Vocabulary — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html  
[47] Loguru recipes (security) — https://loguru.readthedocs.io/en/stable/resources/recipes.html  
[48] HHS HIPAA Security Rule — https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html  
[49] GDPR Article 25 — https://gdpr-info.eu/art-25-gdpr/  
[50] OWASP Secrets Management — https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html  
[51] pip-audit (PyPI) — https://pypi.org/project/pip-audit/  
[52] Bandit docs — https://bandit.readthedocs.io/en/latest/  
[53] Bandit plugins — https://bandit.readthedocs.io/en/latest/plugins/index.html  
[54] OWASP Vulnerable Dependency Management — https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html  
[55] Fowler – Practical Test Pyramid — https://martinfowler.com/articles/practical-test-pyramid.html  
[56] Pact docs — https://docs.pact.io/  
[57] coverage.py Branch coverage — https://coverage.readthedocs.io/en/latest/branch.html  
[58] coverage.py Config / fail_under — https://coverage.readthedocs.io/en/latest/config.html  
[59] diff-cover (PyPI) — https://pypi.org/project/diff-cover/  
[60] pytest Fixtures — https://docs.pytest.org/en/stable/how-to/fixtures.html  
[61] pytest Good practices / strict / src-layout — https://docs.pytest.org/en/stable/explanation/goodpractices.html  
[62] pytest CI — https://docs.pytest.org/en/stable/explanation/ci.html  
[63] pytest-asyncio — https://pytest-asyncio.readthedocs.io/en/stable/index.html  
[64] Hypothesis — https://hypothesis.readthedocs.io/en/latest/  
[65] mutmut — https://mutmut.readthedocs.io/en/latest/  
[66] Cockburn – Hexagonal Architecture — https://alistair.cockburn.us/hexagonal-architecture/  
[67] Martin – The Clean Architecture — https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html  
[68] import-linter (PyPI) — https://pypi.org/project/import-linter/  
[69] Import Linter layers — https://import-linter.readthedocs.io/en/stable/contract_types/layers/  
[70] Import Linter acyclic_siblings — https://import-linter.readthedocs.io/en/stable/contract_types/acyclic_siblings/  
[71] Cosmic Python – Abstractions — https://www.cosmicpython.com/book/chapter_03_abstractions.html  
[72] Cosmic Python – Project structure — https://www.cosmicpython.com/book/appendix_project_structure.html  
[73] Fowler – Bounded Context — https://martinfowler.com/bliki/BoundedContext.html  
[74] Python tutorial – Modules — https://docs.python.org/3/tutorial/modules.html  
[75] FDA CDS Software guidance — https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software  
[76] FDA CDS FAQs — https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs  
[77] FDA SaMD hub — https://www.fda.gov/medical-devices/digital-health-center-excellence/software-medical-device-samd  
[78] ONC HTI-1 Final Rule (89 FR 1192) — https://www.federalregister.gov/documents/2024/01/09/2023-28857/health-data-technology-and-interoperability-certification-program-updates-algorithm-transparency-and  
[79] FDA/IMDRF Good Machine Learning Practice — https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles  
[80] FDA Premarket Submissions for Device Software — https://www.fda.gov/regulatory-information/search-fda-guidance-documents/content-premarket-submissions-device-software-functions  
[81] FDA Cybersecurity in Medical Devices (2026-02) — https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cybersecurity-medical-devices-quality-system-considerations-and-content-premarket-submissions  
