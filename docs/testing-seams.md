# 测试接缝登记（测试只写在预先确认的接缝上）

写新测试前先在这张表里找接缝；找不到就先确认接缝，不要对着内部实现写测试。
接缝 = 可观察行为的公共边界。表里「明确不覆盖」一列同样重要：它挡住「顺手把每层都测一遍」的膨胀。

| 接缝 | 覆盖方式 | 明确不覆盖 |
|---|---|---|
| `medicalrag_core` 领域规则（Run 状态机、Ingestion Run 九阶段状态机、意图树、Safety Boundary、Evidence Fusion、Chunking、身份与会话） | `packages/medical-core/tests/test_*.py`：纯输入输出，无 I/O | 真实中间件、HTTP、模型输出质量 |
| 核心端口（Memory / IntentClassifier / Retriever / Generator / Reranker / RunRepository） | `test_pipeline*.py`、`test_stream.py`：内存 fake 端口 | 适配器的真实实现与供应商行为 |
| 持久化（PostgreSQL 方言） | `packages/infra/tests/test_*repo*.py`、`test_memory.py`：`MEDICALRAG_TEST_DATABASE_URL` 设了即走真库（每个用例前后清 schema），否则内存 SQLite | 上层编排与安全策略；`-m integration` 标记的用例只有迁移漂移与用户往返两条（其余仓储用例靠该环境变量切库，不靠标记） |
| HTTP API（路由 + Pydantic 契约 + 认证/授权） | `apps/api/tests/*`：ASGI transport + 内存 SQLite | 真库方言语义（由上一行覆盖） |
| OpenAPI → TS 类型漂移 | `pnpm --filter @medicalrag/web contract-check` | 破坏性变更判据（只挡「忘记重新生成」） |
| Aegra / LangGraph 图与 v2 消息契约 | `apps/agent/tests/test_graph.py` | Aegra 真实进程与传输层 |
| Aegra authenticate（Cookie → 会话 → 工作区隔离） | `apps/agent/tests/test_agent_auth.py`：进程内 fake Redis/membership | 真实 Redis TTL 与 PG 方言 |
| External Model Provider 适配（Generation / Embedding / Reranker / MinerU Extraction） | `packages/infra/tests/test_llm_*.py`、`test_providers_ext.py`：httpx mock transport | 供应商真实可用性、配额与限流 |
| ModelRouter 三态熔断与候选解析 | `packages/infra/tests/test_routing.py`：内存 fake target repo | 真实 HTTP 首包超时与多候选故障转移编排（由 RoutingGenerator 运行时承担，当前无载体） |
| Ingestion Run 九阶段流水线 | `apps/worker/tests/test_worker.py`：端口 fake + broker 配置探针（只钉我们自己的配置：延迟队列常量、quorum 队列默认值、中间件类型） | **RabbitMQ 真实投递与重投当前无载体**（整个集成层只有 2 条 marked 用例，均非 broker）；需真 broker 时补 compose test profile 集成用例，不要用假 broker 冒充 |
| 检索指标（Recall@k、MRR/nDCG、空召回率、P95） | `eval-retrieval` fixtures + 下限判定（`_MIN_METRICS`，PR 级跌破即红）、`apps/evaluation/tests/test_metrics.py`（指标实现） | **真实检索器不在本链路内**：候选集与分数来自 fixtures，Qdrant dense+sparse、融合与重排的回归**无信号**；Evidence Answer 质量（`eval-answer`，RC 级，且当前无 CI 载体） |
| 门禁判定逻辑（`scripts/ci/*`） | `scripts/ci/tests/test_check_patch_coverage.py`：对齐守卫与同名文件消歧的纯判定函数 | git 子进程与 diff-cover 调用本身（由 CI 现场的真实 diff 与报告覆盖） |
| 浏览器可见行为 | `apps/web/e2e/*.spec.ts`：只面向用户可见属性定位（角色 + 无障碍名称，不用内部 DOM 槽位） | 实现细节（DOM 结构、内部函数）、第三方站点。**当前无 CI 载体**：E2E 属本地/发布流程（需 compose 全栈与真实 provider），接入 CI 的前提是先本地连续稳定通过 |
| 前端 API 请求层 | `apps/web/src/lib/api.test.ts`：桩掉网络边界（`fetch`） | 组件渲染（本仓无 jsdom，不测组件内部） |

## ONC HTI-1 干预风险管理八特征（质量 rubric，非认证）

对齐 ONC HTI-1（89 FR 1192）对 Predictive DSI 的八特征风险分析框架，映射到本仓**已有接缝**。这是产品风险 rubric 与评测覆盖地图，**不是** SaMD/器械认证声明；空白项表示当前无机器信号，补测前先登记接缝。

| 特征 | 现有信号 / 接缝 | 明确未覆盖 |
|---|---|---|
| validity（有效性） | `eval-retrieval`（Recall@k/MRR/nDCG，fixtures 下限）+ `eval-answer`（RAGAS，RC 级） | 真实检索器回归（见检索指标行）；专家安全审核不可被分数替代 |
| reliability（可靠性） | 领域状态机/策略单测；确定性 ChatPipeline；migration `alembic check` | 长时运行漂移、供应商侧可用性 |
| robustness（稳健性） | ModelRouter 三态熔断；ingestion 失败路径；取消/超时用例 | 对抗/对抗性查询集；极端 payload 的系统 fuzz |
| fairness（公平性） | — | **无信号**：需要标注查询集 + 分组检索/回答差距度量；有接缝后再补 |
| intelligibility（可解释性） | Citation → Evidence 可达；Safety Boundary 文案 | 非专家用户可理解性研究；隐藏推理不可外露（产品红线） |
| safety（安全） | Safety Boundary 单测；Evidence Answer vs Clinical Decision 术语闸；CONTEXT.md | 临床专家对高风险意图的抽样审核流程（流程项，非单测） |
| security（安全） | gitleaks；鉴权/工作区隔离；pip-audit；包边界 | 镜像 digest 钉版（威胁模型 T8 残留） |
| privacy（隐私） | 日志 `SAFE_FIELDS` 白名单 + `diagnose=False`；禁落盘 prompt/患者标识 | 日志字段全量审计自动化（当前靠测试 + 评审） |

## 加测试前的三个自问

1. 这个行为属于上表哪一行？不在表里 → 先确认接缝再写。
2. 断言里有没有重算实现？（同义反复：期望值必须来自规范、契约或已知字面量，不能把实现再写一遍。）
3. 会不会因为重构而红？（会 → 测到了实现细节，不是接缝。）

## 删除判据

零增量覆盖的测试、重构时必须跟着改的测试、同一行为且无沟通价值的重复用例——删掉仍够用即删。
