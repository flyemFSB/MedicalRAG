# AI coding 语境下的 TDD 与测试分层最佳实践（外部一手来源调研）

- 日期：2026-09-14
- 性质与来源限定：外部一手来源调研（TDD 原点文献、框架/厂商官方文档、arXiv 论文与工业界实测）；未读取本仓库任何测试用例、测试正文或 fixture 数据，本仓信息仅取自 `AGENTS.md`、各 `pyproject.toml`、`apps/web` 配置、`ci.yml` 与 `docs/*.md` 的门禁**配置形态**；结论只在被方案/ADR 引用时生效。

## 一、结论清单

记号：**【直】**=直接证据（原文可逐字核对）；**【半】**=一手页面未能直连，引文来自搜索服务对**原始 URL** 的抽取片段（见第五节）；**【推】**=研究者推断，非来源陈述。

1. Canon TDD 是**五步**、第一步是「写测试场景清单（Test List）」，不是被广泛流传的三步 —— 来源：[Kent Beck, *Canon TDD*](https://newsletter.kentbeck.com/p/canon-tdd)。**【直】** 置信度：高。
2. 作者本人明说这**不是「你该怎么做」**（"What follows is NOT how _you_ should _do_ TDD"），并给出「重构是可选项」「过早抽象/超出本次需要重构」为错误项 —— 同上一手页。**【直】** 置信度：高。**推论边界：不教条 ≠ 无纪律**，同一页把「删断言让测试假装通过」「把重构混进让测试通过」列为明确错误。**【直】**
3. 「够了」的官方判据是情绪而非覆盖率："Keep testing & coding until your fear for the behavior of the code has been transmuted into boredom." —— 同上。**【直】** 置信度：高。
4. 主流三步简式确实漏掉了 Test List 首步，Fowler 2023-12-11 才在 bliki 补上（原帖 2005-03-05） —— [Fowler, *Test Driven Development*](https://martinfowler.com/bliki/TestDrivenDevelopment.html)。**【直】** 置信度：高；「Test List 段落即该次改稿新增」为**【推】**（Fowler 只写了改稿动因，未逐字说明改了哪段）。
5. 金字塔（低层多、高层少）**唯一**豁免条件是高层测试「快、稳、易改」，否则默认仍站金字塔；中间层官方所指就是**皮下测试（API 层）** —— [Fowler, *Test Pyramid*](https://martinfowler.com/bliki/TestPyramid.html)。**【直】** 置信度：高。
6. 高层测试是第二道防线：高层抓到 bug 说明**还缺一个（或写错了）低层测试**，修 bug 前必须先在低层复现 —— 同上。**【直】** 置信度：高。
7. Google 官方分层维度不是 unit/integration 而是 **size + scope**；`small` 禁止 I/O/网络/sleep、只能上 test double；`medium` 允许多进程与**到 localhost** 的调用、禁止访问非 localhost 远端；`large` 主要用于**验证配置**与无法替身的遗留组件 —— [*Software Engineering at Google* ch11](https://abseil.io/resources/swe-book/html/ch11.html)。**【直】** 置信度：高。
8. Google 官方配比是 **80/15/5**（narrow unit / medium integration / e2e）；广泛流传的 70/20/10 **未能在一手页面核实**（见第五节） —— 同上。**【直】** 置信度：高（仅对 80/15/5）。
9. 覆盖率是**找盲区**的工具、不是质量的数字表述；把它当靶子会出现「80% 从地板变天花板」；Google 建议**只用 small 测试量覆盖率**以避免大测试造成的覆盖率虚高 —— 同上 + [Fowler, *Test Coverage*](https://martinfowler.com/bliki/TestCoverage.html)。**【直】** 置信度：高。
10. 唯一可操作的**删除**判据是「删掉一些测试后仍然够用」；「太多」的症状是「改代码时改测试比改代码更累」；具体机制是 **delta coverage**——零增量覆盖的测试应删，除非它有沟通价值 —— Fowler *Test Coverage* 与 [*Is TDD Dead?* 纪要](https://martinfowler.com/articles/is-tdd-dead/)。**【直】** 置信度：高（引语归属见第五节）。
11. 大测试的边界应设在 **UI/API 之间**，且**不测真实第三方**（第三方依赖本身就是拆分层级的缝） —— [*SWE at Google* ch14](https://abseil.io/resources/swe-book/html/ch14.html)。**【直】** 置信度：高。
12. E2E 官方定位：验证**用户可见行为**、不依赖实现细节（函数名/CSS class/DOM 结构）、测试间**完全隔离**、**只测你能控制的东西**、定位器优先面向用户的属性与显式契约 —— [Playwright Best Practices](https://playwright.dev/docs/best-practices)。**【直】** 置信度：高。
13. LLM 生成测试的工业实测呈「三角作业」：75% 的类含至少一个能编译的用例 → 57% 含能稳定通过的 → **仅 25%** 含「能编译 + 稳定通过 + 有新增行覆盖」的；经机器过滤器后人类工程师接受率 **73%** —— Meta TestGen-LLM，[arXiv:2402.09171](https://doi.org/10.48550/arxiv.2402.09171) / FSE 2024 Industry。**【直】** 置信度：高。**同源两面**：既证明「LLM 测试有用（需硬过滤器）」，也证明「能跑通 ≠ 有价值」（32 个百分点落差）。
14. **80.2%** 的 agent 生成测试补丁只含弱断言或无断言；新建测试文件的强断言率随 agent 从 18% 到 67% 不等；feature PR 的强断言率仅 **18.2%**（bug fix 25.6%、test-focused 24.9%）；作者结论「测试文件数会**系统性高估**验证强度」 —— [arXiv:2606.18168](https://arxiv.org/html/2606.18168)。**【直】** 置信度：中（2026 预印本，录用信息未核实）。
15. 覆盖率与故障检出率**脱钩**：人类与 LLM 测试的行/分支覆盖几乎相同（84.8%/88.5%、75.2%/82.1%），故障检出率却是 17.2% vs 69.0%（p<0.001）；作者称之为「覆盖率不是可靠测试质量代理」的最清晰实证 —— [arXiv:2606.08588](https://arxiv.org/html/2606.08588v1)。**【直】** 置信度：中。
16. **先写实现再让模型补测试**，故障检出率从 25% 掉到约 **14%**；作者命名为 error propagation，并指出高覆盖率与高通过率可能只是「错误实现与错误测试互相印证」；作业结论是「保持规范/实现/验证之间的隔离度」 —— [arXiv:2607.05139](https://arxiv.org/pdf/2607.05139)。**【直】** 置信度：中。
17. LLM 生成的 oracle **倾向于记录「实际实现行为」而非「期望行为」**；模型自查断言正确率不足 50%（因此不能自审）；命名退化（`a`/`b`/EvoSuite 式命名）使 oracle 质量最多下降 16.10% —— [arXiv:2410.21136](https://arxiv.org/html/2410.21136)。**【直】** 置信度：中高。
18. 用「自己生成的测试」反复精修代码会把 test overfitting 率抬到 **25.5%**；末尾结论是 "we caution against over-reliance on tests during code generation" —— [arXiv:2511.16858](https://arxiv.org/pdf/2511.16858)（FSE 2026）。**【直】** 置信度：中。
19. 把「通过率」变成信号的**最短路**是要求 fail-to-pass（先在旧代码失败、改后通过）：只保留 F→P/P→P 的补丁，精度翻倍到 **47.8%**，代价是召回降到 **20%** —— SWT-Bench，[NeurIPS 2024 PDF](https://openreview.net/notes/edits/attachment?id=UcRNq9MwjP&name=pdf)。**【直】** 置信度：中高。
20. 三家厂商官方立场均把**「可跑的验证回路」**列为最高杠杆，**无一家把「实现完成后补测试」写成推荐做法**：Cursor 唯一给出明确五步 TDD（写测试 → 确认失败 → **提交测试** → 让 agent 写实现且**不得修改测试**）；Anthropic 要求「可跑检查 + 独立上下文审查（干活的人不判分）+ bug 场景先写复现失败测试」；OpenAI 要求 done when 含测试、自己跑相关检查、交付证据 —— [Cursor](https://cursor.com/blog/agent-best-practices)、[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)、[Codex Best Practices](https://developers.openai.com/codex/learn/best-practices)。**【直】** 置信度：高。
21. 官方同时给出了反过度工程限制：被要求找缺口的评审**总会报出缺口**，逐条追会直接导致「额外抽象层、防御式代码、为不可能发生的情况写测试」 ——同上 Claude Code 官方页。**【直】** 置信度：高。
22. METR 随机对照试验（16 名资深开源开发者、246 个任务、**在自己熟悉的成熟仓库**上）：允许用 AI 时完成时间**慢 19%**，而他们事前预期 +24%、事后仍自认 +20%；论文特别指出「质量标准极高、隐式要求多（文档/测试覆盖/lint）」的场景 AI 收益可能更低 —— [METR 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)。**【直】** 置信度：高（外推限制见第五节）。
23. DORA 2024（39,000+ 受访者的横断面调查）：AI 采用每 +25%，吞吐约 **−1.5%**、**稳定性约 −7.2%**；官方对策措辞是「小批量与稳健测试这些基本功仍然关键」 —— [DORA 2024](https://dora.dev/research/2024/dora-report/)。**【直】** 置信度：高（横断面统计，非因果）。
24. Google 的 flaky 基线：约 **1.5%** 的测试运行报 flaky、**16%** 的测试有某种程度 flakiness、**84%** 的 pass→fail 转变涉及 flaky；官方同时警告自动 quarantine **会掩盖真 race condition** 并产生「狼来了」效应 —— [Google Testing Blog 2016-05](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)。**【半】** 置信度：高（内容一致性见第五节）。
25. 官方认定的覆盖率门禁**位置是变更行**（patch/changelist），不是全仓总量：per-commit 目标 99% 合理、90% 是合理下限，且明确「项目级 90% 以上多半不值得」；Google 不强制全仓统一阈值、给团队自选参考档（60/75/90） —— [Google Testing Blog 2020-08](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)。**【半】** 置信度：中（见第五节）。
26. 「总覆盖率当质量目标」有一手实证否证：31,000 个测试套、5 个最大 724k 行的系统，结论是覆盖率「可用于识别测试不足的部分，但不应作为质量目标」 —— Inozemtseva & Holmes, ICSE 2014 Distinguished Paper（[PDF](https://cs.uwaterloo.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)）。**【直】** 置信度：高。
27. 静态检查作为一层有官方依据：TS/ESLint 这类工具「能给你相当可观的置信度」 —— [Kent C. Dodds, *Write tests. Not too many. Mostly integration.*](https://kentcdodds.com/blog/write-tests)。**【直】** 置信度：高。**同时是反例来源**：同一作者自认「70% 之后收益递减」这个数字「是我编的，没有科学依据」——任何百分比阈值都不得当作实证结论。**【直】**

## 二、「正好完整」的定义（逐层）

前置两条层间规则（一手）：①**高层测试是第二道防线**——高层每次抓到 bug，都要回填一个低层测试（[Fowler, Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html)）；②**豁免金字塔的唯一条件是高层测试快、稳、易改**，否则不成立。其余各层的「正好完整」由下表的五问定义。

### 1. 静态检查（格式 / lint / 类型 / 包边界 / 生成物漂移 / 密钥与依赖审计）
- **负责**：语法与风格一致、类型形状、依赖方向（`medical-core` ↛ 框架；`apps/*` 互不 import）、自动生成物与源无漂移（OpenAPI TS 类型）、密钥与已知漏洞。本仓形态：ruff format/lint、`oxlint`/`oxfmt --check`、`pyright(basic)` + `tsc -b`、`check_package_boundaries.py`、`contract-check`、gitleaks、pip-audit/pnpm audit（`ci.yml`）。
- **明确不负责**：任何**运行时行为**语义——取值边界、状态机不变量、事务/并发语义、医疗安全边界（「不生成无证据支持的个人临床决策」）。依据：Google 的 size/scope 二分里，静态检查对应零执行路径，scope 为空（ch11）。
- **写的成本上限**：**不新增文件**；规则加在共享配置，不写 per-file 例外。本仓现状即上限：`pyright` 为 `basic`、ruff 的 `extend-exclude` 只排除 `*.md`。一条规则 = 一行配置。
- **加触发条件**：同类缺陷**第二次**由同一条规则可拦（第一次算偶然）；某生成物漂移在人工流程中漏过一次。依据：官方经验是「一旦设成指标就会被当目标」（ch11 覆盖率反面案例的同类失效模式）——【推】泛化。
- **删/合并触发条件**：规则与 formatter 互相打架；100% 只产出格式噪音；已被更上层门禁完全覆盖（如 `tsc -b` 覆盖某条 lint）。

### 2. 单元（`medical-core` 规则/状态机/策略/端口契约，内存适配器）
- **负责**：领域规则、状态转换、策略判定、确定性 `ChatPipeline`、领域异常分类、端口协议的语义契约。参照 Google `small` 的硬定义：单进程、无 sleep、无 I/O、无网络、无阻塞调用，替身只能用 test double（ch11）。
- **明确不负责**：真中间件行为（PG/Redis/Qdrant/RabbitMQ）、迁移与真实 SQL、并发/事务/幂等语义、HTTP/SSE 形状、模型输出质量与医疗内容正确性。依据：`small` 明确禁止网络与磁盘；Fowler 关于 classic TDD「能用真对象就用」在此层被 I/O 禁用覆盖。
- **写的成本上限**：必须落在 `small` 档；一个用例只断言一个行为信号；参数化的一个参数集 = 一个**独立可定位**的用例（[pytest 官方 parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)）；先写 Test List 再落代码（Canon TDD 第 1 步），Test List 是设计工件、不落进仓库。
- **加触发条件**：新增/修改领域规则、状态转换、不变量；**任何高层测试抓到的 bug（先回填到本层再修）**；某个缺陷在生产或评测中出现过一次。
- **删/合并触发条件**：**零增量覆盖**的测试（delta coverage，Fowler 纪要）；重构时必须跟着改的测试（结构敏感；Dodds 判据「重构时几乎不该改测试」）；两个测试断言同一行为且**无沟通价值**（唯一豁免项）。
- **已知执行缺口（本仓）**：本层「无 I/O、无网络」目前靠约定，无机器强制（无 pytest-socket 类插件）；`fail_under=80` 是全仓总覆盖率，不区分本层。

### 3. 契约（FastAPI OpenAPI、事件 envelope、Agent Protocol v2 对 Aegra、provider 适配器）
- **负责**：对外形状与协作契约的稳定性——路由/schema 形状、事件 envelope 字段语义、与 Aegra 的 Agent Protocol v2 一致性、provider 适配器的边界形状。本仓形态：`contract-check`（openapi-typescript `--check`）+ pytest 契约用例（`ci.yml` python job 的 "Unit & contract tests" 步骤）。
- **明确不负责**：业务规则正确性（属单元）、真中间件一致性（属集成）、UI 可用性（属 E2E）、以及 schema **表达不了的**语义约束（例如「不得生成无证据支持的临床决策」无法写进 OpenAPI）——【推】。
- **写的成本上限**：能从 schema 自动派生的契约**不要手写**——Schemathesis 官方定位即「无 per-endpoint 测试需要维护，指向 schema 即跑」，且默认同时做正向与负向（[官方文档](https://schemathesis.readthedocs.io/en/stable/)）；手写契约只覆盖 schema 表达不了的协作契约。本仓硬规则：改路由/Pydantic 模型必须**同 commit** 带生成产物。
- **加触发条件**：路由或模型改动（强制）；新增 provider 适配器；出现第二个 TS 消费者（ADR 0071 判据）；**契约破坏性变更**（删字段/改必填/收窄类型）——这类应触发 ADR 而非新测试【推】。
- **删/合并触发条件**：能用 schema 派生替代的手写契约；与另一份契约断言同一字段且**不能独立失败**；契约对象已下线（ADR 0060 deletion test）。
- **已知执行缺口（本仓）**：现有门禁只防「忘记重新生成」（漂移），**不防破坏性变更**——只要生成产物同步更新就全绿。

### 4. 集成（Compose `test` profile：PG / Redis / Qdrant / TaskIQ + outbox）
- **负责**：真中间件上的交互语义与配置接线——迁移与 schema 漂移（`alembic check`）、唯一约束去重、outbox relay、重试/死信语义、仓储的真实 SQL 行为。对齐 Google `medium`：可跨进程、可阻塞、**只允许连 localhost**；Testcontainers 官方的动机正是「内存替身未必具备生产服务全部特性」（[官方文档](https://testcontainers.com/getting-started/)）。
- **明确不负责**：UI/用户流程、模型质量、跨服务的完整业务验收、性能 SLO（本仓无性能层）。
- **写的成本上限**：`medium` 档（单机、仅 localhost）；一个用例只验证「一个真实依赖上的一个交互语义」；不得引入第二个编排器（AGENTS.md / ADR 0055 已禁第三方编排器），因此集成必须挂在既有 compose `test` profile 上，不新造框架。
- **加触发条件**：新增/改动迁移、唯一约束、幂等键；outbox/重试/死信语义改动；单测层用替身掩盖了可疑差异（Testcontainers 官方给出的正是「内嵌服务行为略异」这一动机）。
- **删/合并触发条件**：同语义已被同层或更低的单测等价覆盖、仅剩启动成本；第 N 个等价连通性 smoke（保留一个即可）；**长期 flaky** 的用例——官方警告 quarantine **会掩盖真 bug**，因此先修或降级，不做静默隔离。

### 5. E2E（Playwright：登录 / 聊天流 / 来源 / 反馈 / 管理流）
- **负责**：用户可见行为与整体接线的联调——每条主流路径「从入口到可见结果」。官方定位：测用户可见行为、不依赖实现细节、不测第三方（Playwright Best Practices）。
- **明确不负责**：实现细节（函数名、DOM 结构、CSS class）、第三方站点/外部服务、穷举边界取值（属单元/契约）、跨浏览器矩阵（本仓仅 chromium project）、性能。
- **写的成本上限**：合并级才跑（ADR 0080）；仅 chromium、`retries: 0`、一条路径一个 spec；官方允许「为了更清晰可读而保留少量重复」。数量上限：应比契约/单测小一个数量级（Google 80/15/5 是唯一官方配比参考；**把它映射到本仓是本稿推断**）——【推】。
- **加触发条件**：某个用户可见流程**首次贯通**；发布前必须验证的配置/接线（Google `large` 的定位正是「更多是验证配置而非代码片段」）；**UI 改动的完成判据**——本仓规定必须在浏览器里实际跑通（AGENTS.md）。
- **删/合并触发条件**：同一行为已能被皮下/契约层覆盖（ch14 明确建议把测试拆到 **UI/API 边界**）；失败只能靠实现细节定位、换成面向用户定位器后仍定位不了的用例；出现 flaky（本仓 `retries: 0` 意味着 flaky 直接红）。

### 6. 评测（`eval-retrieval` 确定性检索指标 / `eval-answer` RAGAS）
- **负责**：检索质量（Recall@k、MRR/nDCG、Top-1 命中、空召回率、P95，PR 级、无外部服务）与答案质量（RAGAS，RC 级）。本仓形态：`ci.yml` 直接跑 `eval-retrieval`。
- **明确不负责**：**替代专家安全审核**（AGENTS.md 原文：任何 RAGAS 分数都不能替代专家安全审核）；代码正确性（属单元/契约）；医疗结论的临床有效性。
- **写的成本上限**：只有**有可解释 ground truth** 时才扩 fixture；阈值必须**跑出基线再钉值**，不得先定数字；RAGAS 在隔离解释器运行（不共存于主 lock），因此答案评测天然不能成为提交级门禁。
- **加触发条件**：改动检索/分块/排序/RRF 参数/prompt/模型；新增带 ground truth 的 fixture；某一类错误在生产中首次出现。
- **删/合并触发条件**：对任何已知改动都**不改变数值**的 fixture（零判别力，即 delta coverage 的评测版）——【推】；阈值在无 ADR 记录的情况下被放宽过。
- **已知执行缺口（本仓）**：fixture 路径硬编码在 CI 命令中，数据集本身无「不得与实现同批修改」的护栏。

## 三、AI coding 专属反模式（实测失败模式 → 护栏 → 在哪一层拦）

1. **弱断言 / 无断言（Unknown Test）** —— 实测：80.2% 的 agent 测试补丁含弱断言或无断言；feature PR 强断言率仅 18.2%；LLM 生成套里 "Unknown Test" 占 47%–51%，"Magic Number Test" 覆盖 85%–100%。**护栏**：把「新用例是否含显式断言、断言是否比对期望值」做成机器检查（依据 E-2 的 oracle 分类法；**具体检查形态为研究者建议**）。**在哪一层拦**：单元 + 契约（新用例必过断言检查）；E2E（定位器只允许面向用户属性，避免"能跑没断言"的路径）。
2. **Oracle 复制实现** —— 实测：LLM 生成的断言倾向于记录**实际实现行为**而非期望行为。**护栏**：断言值从**规范/契约**派生而非从实现反推；用例先有 Test List（期望行为清单）再落代码；契约层优先用 schema 派生断言（schema 派生天然不受当前实现偏置）。**在哪一层拦**：单元（写断言的人不得同时是写实现的人——Anthropic 官方"独立的 Claude 写测试"同构）+ 契约（schema 派生）。
3. **Error propagation / 自我确认** —— 实测：先写代码后补测试，检出率 14% vs 25%；「高覆盖率 + 高通过率」可能只是互相印证。**护栏**：强制 **fail-to-pass**——用例必须先在旧代码上失败、改动后通过，并把两段输出留证。**在哪一层拦**：单元（红→绿两段证据）；契约（schema 变更前后差异）；评测（阈值基线前后对比）。
4. **测试过拟合** —— 实测：用自生成测试反复精修 → 过拟合率 25.5%；即使把 golden tests 交出去，仍会破坏其它回归测试。**护栏**：被验证的补丁**不得同时修改判定它的测试**；补丁过滤只保留 F→P（精度 47.8%、召回 20%，即**只提高精度，要用更宽的召回兜底**）；评测 fixture 视为 holdout。**在哪一层拦**：单元（禁止同批改测试）+ 评测（holdout 隔离 + 禁止单测 import 评测 fixture）。
5. **覆盖率虚高** —— 实测：覆盖近似相同而检出率差 4 倍；总覆盖率「80% 从地板变天花板」；官方要求只从小测试量覆盖率。**护栏**：门禁用**变更行覆盖**（patch/changelist）而非全仓总覆盖率；总覆盖率保留为盲区看板。**在哪一层拦**：门禁层（CI 的覆盖率口径），并区分「单元层覆盖」与「大测试覆盖」两个数字。
6. **把测试文件数当门禁** —— 实测：文章明确「测试文件数会系统性高估验证强度」。**护栏**：统计口径改为「含强断言的用例数」，不是文件数/用例数。**在哪一层拦**：单元 + 契约的统计口径（**落地形态为研究者推断**）。
7. **命名退化与常量魔法值** —— 实测：命名规范退化使 oracle 质量最多下降 16.10%；断言歧义（Assertion Roulette）在 Zero-Shot 下 54.77%、在结构化提示下 20.94%（说明这是**可控变量**）。**护栏**：领域正名（CONTEXT.md）先行；测试函数用行为命名；提示顺序走「Test List → 单条用例化 → 命名」而不是一次性批量生成。**在哪一层拦**：单元（命名与常量）+ 静态检查（禁止占位符命名的 lint 规则形态）。
8. **同一个 agent 既写实现又写判定** —— 实测：模型自查断言正确率不足 50%。**护栏**：独立上下文审查——"the agent doing the work isn't the one grading it"（Anthropic 官方）+ 交付必须附命令与原始输出。**在哪一层拦**：审查/门禁层（CI 机器门禁 + 独立 reviewer），不依赖自评；不允许「模型说过了」作为完成证据。
9. **无证据的「完成」断言（绿灯 ≠ 完成）** —— 实测：METR 明确区分任务成功定义「人类认为能通过 review（含风格/测试/文档要求）」与 benchmark 的「自动测试打分」；官方要求提供 test 输出、命令与返回。**护栏**：PR/交付必须含**实际执行的本地等价命令与结果**。**在哪一层拦**：全层（门禁入口）；本仓已有对应形态：AGENTS.md 要求门禁命令清单与实际浏览器验证。
10. **评审驱动的过度工程** —— 实测：被要求找缺口的评审总会报出缺口，逐条追导致额外抽象层、防御式代码、为不可能发生的情况写测试。**护栏**：审查以**删减**为口径（本仓 AGENTS.md 已强制 ponytail 审查），门禁**不因评审意见而增测试**，只在有失败证据时增。**在哪一层拦**：静态检查 + 审查层（diff 级删减审查），并禁止「为假想需求加层」。
11. **E2E 依赖第三方或实现细节** —— 官方反例：不测你不控制的外部站点/服务；DOM 结构变化不该让测试红。**护栏**：外部边界 mock 掉、定位器只用面向用户属性与显式契约、每用例完全隔离。**在哪一层拦**：E2E。
12. **靠重试掩盖 flaky** —— 官方警告：quarantine 会掩盖真 race condition；「狼来了」使人忽略告警。**护栏**：不自动重试掩盖（本仓 Playwright `retries: 0` 已符合方向）；隔离必须留痕、计入可见列表并关单。**在哪一层拦**：集成 + E2E。

## 四、本仓门禁差距表

| 现有门禁 | 依据来源 | 差距 | 结论性建议 |
|---|---|---|---|
| `[tool.pytest.ini_options]` 只声明 marker `integration`，无 `--strict-markers`；集成靠「未设环境变量自动跳过」 | 根 `pyproject.toml`；AGENTS.md；pytest 官方 mark 文档（未注册 marker 只 emit warning，`strict_markers` 才报错） | 拼错 marker 或 `-m` 表达式写错会**静默跑空且全绿**，门禁不可观测 | 门禁形态结论：补 `--strict-markers`；CI 显式 `-m "not integration"`，用「显式排除」替代「静默 skip」 |
| 覆盖率 `fail_under=80` + `term-missing`，`source` 为全部六个 src 包，`omit` 掉 tests/migrations | 根 `pyproject.toml`；Google ch11「只用 small 测试量覆盖率」；Google 2020 博文（变更行 99%/90% 下限）；Inozemtseva & Holmes ICSE 2014 | ① 全仓总覆盖率是唯一阈值，未区分单元层与大测试层；② 未定位到变更行，历史欠债会长期压住新增代码；③ 只有下限、无「未覆盖项上限」表达；④ 集成/E2E 执行到的代码会抬高分母（覆盖率虚高） | 结论：门禁主指标改为**变更行覆盖**；总覆盖率降为看板指标；单元层覆盖率单独统计（排除大测试贡献）；阈值维持 80 不跟风，但口径要换 |
| 契约层只有 `contract-check`（openapi-typescript `--check`）漂移门禁 | `ci.yml`；`apps/web/package.json`；AGENTS.md（ADR 0071） | 只防「忘记重新生成」，**不防破坏性变更**（删字段/改必填/收窄类型只要产物同步就全绿） | 结论：这是契约层最高价值缺口——PR 级加**破坏性变更判据**（对 schema 基线做 diff），并把「契约破坏需 ADR」写成判据 |
| 提交级与 PR 级门禁由 `ci.yml` 机器强制（ruff/pyright/包边界/eval-retrieval/pytest --cov/前端 `check`/安全审计） | `ci.yml`；AGENTS.md | ① **合并级门禁（Compose 集成 + 迁移测试 + E2E + eval-answer）在仓库内无任何机器载体**，仅本地命令；② `docker` job「四镜像 build」实际跑在 **PR 级**，超出 AGENTS.md 声明的层级 | 结论：二选一并写进文档——要么补一个合并级/定期 workflow 承载集成+E2E+eval-answer，要么把 AGENTS.md 措辞改为「合并级由本地等价命令执行」；镜像构建的层级声明与 `ci.yml` 对齐 |
| 前端 `apps/web/vitest.config.ts`：仅 `include: src/**/*.test.{ts,tsx}` + `environment: node`；`check` = lint/typecheck/test:unit/build/fmt:check | `apps/web/vitest.config.ts`、`package.json`、`ci.yml` | 前端**无覆盖率门禁**（无 `coverage.thresholds`）；单测只跑一层；UI 层无单测（环境为 node 非 jsdom）；无 a11y 自动跑 | 结论：前端「无分层」不是问题（vitest 与 playwright 两套 runner 已天然分层），缺的是**阈值形态**——若补覆盖率，用「未覆盖项上限」比百分比更贴合「找盲区」用途；**不建议**为补覆盖率引入 jsdom（YAGNI，出现第二个组件测试消费者再说）；**a11y 是硬要求却无载体**，WCAG 2.2 AA 应有一个自动跑入口 |
| `eval-retrieval` 在 PR 级 CI 运行（确定性、无外部服务）；`eval-answer` 在隔离解释器、无 CI 载体 | `ci.yml`；AGENTS.md；根 `pyproject.toml`（RAGAS 不共存于主 lock） | 评测 fixture 路径硬编码，数据集本身无「不得与实现同批修改」的护栏；答案级评测无机器触发 | 结论：把评测 fixture 当 **holdout**——单元/契约测试禁止 import；阈值必须先跑出基线再钉值；答案级评测不强求进门禁（隔离环境是硬约束） |
| `pyright typeCheckingMode = "basic"`；无 mypy | 根 `pyproject.toml`；`docs/development-standards.md` §1.3（禁 `Any` 隐藏边界） | 「禁止用 `Any` 隐藏边界不确定性」这条目前**只有评审兜底**，无机器判据 | 结论：不急上全仓 strict（成本高、收益未证）；若要机器化，用**局部规则/单点豁免**而不是全局收紧 |
| Playwright `retries: 0`、仅 chromium、`trace: retain-on-failure`；pytest 侧无 flaky 标记或统计 | `apps/web/playwright.config.ts`；Google 2016 flaky 博文（1.5%/16%/84%） | **无 flaky 基线数据**；无隔离/关单流程；集成用例长 flaky 时无处置判据 | 结论：保留 `retries: 0`（方向正确）；**先积累计数**，有数据再决定是否引入隔离机制（无实例不建，YAGNI） |
| dev 依赖仅 pytest / pytest-asyncio / pytest-cov | 根 `pyproject.toml`；Google ch11（small 禁 I/O 与网络） | 单元层「无 I/O、无网络、无阻塞调用」**全靠约定**，无机器强制（无禁网插件、无阻塞调用检测） | 结论：这是本层定义目前唯一执行缺口；出现第一例「单测偷偷联网/读盘」再引入禁网插件（YAGNI） |
| ruff 的 `extend-exclude` 只排除 `*.md`；无测试目录的 per-file 放宽 | 根 `pyproject.toml`；AGENTS.md（测试命名规则） | 测试代码用生产 lint 标准可能误伤（对照：业界标杆对 `tests/**` 有 per-file-ignores） | 结论：不预先放宽；出现第一例误伤再按文件放宽，并优先改测试而不是关规则 |
| E2E：单一 `playwright.config.ts`、一个 chromium project、无登录态复用 setup、无 shard、无 a11y 专跑 | `apps/web/playwright.config.ts`；AGENTS.md（E2E 覆盖登录/聊天流/来源/反馈/管理流；WCAG 2.2 AA 硬要求） | 每条 spec 重复登录（成本）；a11y 无自动化入口（**硬要求无载体**） | 结论：a11y 冒烟是自查出的最高价值补项；登录态复用与 shard 属效率优化，E2E 在合并级且量小，暂不必（YAGNI） |

## 五、未核实项与反方证据

**未能核实（不得作为结论依据）**
1. **70/20/10**（70% 单测 / 20% 集成 / 10% E2E「Google 建议」）在两份草稿与我的复核中均**未能在一手页面出现**；可核实的一手配比是 Google 官书的 **80/15/5**。凡引用比例，只用 80/15/5 并注明出处。
2. **Google Testing Blog 在本环境无法直连**：我实测 `testing.googleblog.com` 直接抓取失败、`web.archive.org` 快照亦失败。2020-08 覆盖率博文与 2016-05 flaky 博文的引文，来自搜索服务对**原始 URL** 的抽取片段；我对两处关键句（60/75/90 三档、per-commit 99%/90% 下限）做了二次检索，索引中逐字一致。**据此标【半】，不标【直】**。两份草稿对此不一致（草稿 A 标未直连、草稿 B 标直接证据），以实测为准取更保守者。
3. **`source_check` 不可用**：本机返回 `missing-evidence`（confidence 0.20），本稿所有引文均未做机器二次核验；上一条的交叉核对以人工检索替代。
4. **arXiv 直连在本环境被阻断**（我实测 `abs` 页 fetch failed）：第一、五节中所有 arXiv 论文数据来自草稿的原文片段，我未直接抓取原页核对。
5. **Google FSE 2019 覆盖率论文 PDF 抓取失败**：Level 1–5 分级表（Level 3 = 项目 ≥60% / changelist ≥70%；Level 5 = 项目 ≥90% / changelist ≥90%）与「Google 不强制全仓阈值」来自索引抽取，未直连核对。
6. **delta coverage 的引语归属**：该句是 Fowler 纪要中**转述** Kent 转述 Herb Derby 的概念，不是 Beck 的署名原句；Derby 本人无可访问原文。
7. `The test list is a first-class artifact` 之类表述在 Canon TDD 正文中不存在（仅见于第三方技能仓库转述），不引用。Kent Beck 的 LinkedIn 原帖返回 HTTP 451；TDD By Example 书内逐字句（PDF 抓取失败）未核实。
8. **Playwright 官方未给出 E2E 数量配额**——这是**缺失性证据**，不能推论成「官方反对配额」。
9. 草稿 B 中 2026 年预印本（2606.18168 / 2606.08588 / 2607.05139 / 2609.05978）的投稿日期与录用状态未核实；VibeCheck 样本仅 15 个学生仓库，置信度低；oracle 分类器与人工标注一致率 86.7%。
10. **「AI 生成的测试是否比人手写测试更 flaky」无一手量化研究**；Google 的 1.5%/16%/84% 数据来自人类维护的测试库，**不能外推到 AI 生成测试**。
11. 对「AI 提速」的两组数字不能折中：**METR RCT −19%**（16 人、成熟仓库、平均 5 年项目经验）vs **Google 内部 RCT +21%~26%（该论文同时声明区间大、未达 p<0.05 显著；另一处报告 t 检验 p=.038）** vs **Copilot 绿色项目任务 +55.8%**。任务性质不同（成熟仓库 vs 一次性企业任务 vs 从零写服务），论文自身都声明不可外推。METR 特别提示「质量标准高、隐式要求多」的场景（文档/测试覆盖/lint）AI 能力可能更低——这一条与本项目最相关。
12. 本仓信息仅来自门禁**配置形态**：本稿未读任何测试用例正文，因此「各层当前实际覆盖了什么」不在本稿结论范围内；`alembic check` 由单元级测试强制一事引自 `docs/version-baseline.md` 的门禁第 8 条，非我阅读测试文件所得。

**反方证据（与本文主张冲突或限定其适用范围）**
1. **DHH《TDD is dead. Long live testing.》(2014)**：明确拒绝 test-first，称 test-first 单元「为避开一切慢操作（数据库、文件 IO、真浏览器）而造出过度复杂的中间对象与间接层」，主张把重心移到系统测试。Fowler 纪要中 Kent 的反驳：把 test-induced damage 归因 TDD「像把车开到坏地方却怪车」；且 DHH 的批评建立在「TDD 必须重 mock」这一假设上，而这不是事实。**对本仓的适用性**：本仓单元层面向无框架依赖的 `medical-core` 领域规则，不存在「为可测性造中间对象」的压力，因此该批评对本仓直接适用性弱——**【推】**。
2. **Google 自家承认「金字塔写得好、执行跑偏」**（2020 *Fixing Test Hourglass*，索引片段，未直连）——说明分层共识在工业界并不自动落地。
3. **Kent C. Dodds 自认覆盖率收益数字无依据**（"I made that number up... no science there"）——任何百分比阈值（含本仓的 80）都不应被当作实证结论，只能当作组织约定。
4. **Trophy /「集成优先」不能给本仓 E2E 提权**：其作者自述 Trophy 只适用于自有代码的单体，且明确不适用于微服务或后端服务；Fowler 的豁免条件被写死为「高层测试快、稳、易改」才成立，默认仍站金字塔。
5. **LLM 生成测试有真实工业价值**：Meta 经硬过滤器后 73% 被工程师接受并落生产；在**有 bug 上下文**的回归场景，带检索的 LLM 测试故障检出率 69% 显著高于仓库既有通用人类测试 17.2%；TDD-Bench 的低分（最好配置 fail-to-pass 23.6%）部分由严格判据造成（要求至少一个 F2P **且**不存在修复后仍失败的测试）。**结论方向**：反模式不等于「不要用 LLM 写测试」，而是「必须有机器过滤器 + 人工签核 + 独立判定」。
6. **提供测试给 LLM 能提升生成代码正确率**（函数级 +9.15%~29.57%，remediation 再 +5.26%~9.02%），但**文件级真实任务只有 +7.27%**——这是「测试先行」在真实仓库尺度上收益缩水的直接反证。
