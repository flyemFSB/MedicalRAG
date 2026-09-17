# 质量与覆盖率门禁最佳实践（外部一手来源 + 本仓门禁配置盘点）

- 日期：2026-09-14
- 性质与来源限定：外部一手来源（厂商官方文档、Google 官书与官方博客、GitHub 官方文档、学术论文、工具官方仓库/文档）+ 本仓**门禁配置形态**盘点。本仓信息仅取自 `AGENTS.md`、`docs/development-standards.md`、`docs/version-baseline.md`、`docs/adr/0080-production-hardening-baseline.md`、`.github/workflows/{ci,integration}.yml`、`.pre-commit-config.yaml`、根 `pyproject.toml`、`apps/web/{package.json,vitest.config.ts,playwright.config.ts}`；同目录既有调研 `docs/research/ai-coding-tdd-best-practices.md` 的已核实项直接引用、不重复调研。**未读取任何测试正文**（`tests/`、`conftest.py`、`test_*.py`、`*.spec.ts`、`*.test.ts`、`fixtures/` 一律未打开），因此「各层实际测了什么」不在本文结论范围内。
- 记号：**【直】**=原文可逐字核对（本次直连抓取）；**【半】**=一手页面未能直连，引文来自搜索服务对**原始 URL/PDF** 的抽取；**【推】**=研究者推断，非来源陈述。每条附置信度。
- 覆盖率实测输入（本次任务提供的实测事实，非本文自行运行）：总量 **75.57%**（4090 statements / 999 missed），在「SQLite / 真 PostgreSQL」×「带 / 不带 `-m` 过滤」四种组合下数字完全相同。

## 一、结论清单

1. **分层的一手总原则是「快且可靠 → 提交前（presubmit）；慢且不确定 → 提交后（postsubmit）」**，且 presubmit 允许损失部分覆盖、由 postsubmit 与回滚兜底 —— [Software Engineering at Google, Ch.23](https://abseil.io/resources/swe-book/html/ch23.html) 原话："CI should optimize quicker, more reliable tests on presubmit and slower, less deterministic tests on post-submit."**【直】** 置信度：高。
2. **presubmit 不放三样东西**：全仓测试（"we typically limit presubmit tests to just those for the project where the change is happening"）、flaky 检查（"the cost of having many engineers affected by them … is too high"）、直连真实生产后端（安全与配额）—— 同源。**【直】** 置信度：高。
3. **官方文本内没有分钟级 presubmit 目标**；可引用的时长经验值只有 Fowler 的「十分钟构建」与「慢测试移到次级构建、可达数小时且不随每次提交运行」—— [Fowler, Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) 原话："For most projects, however, the XP guideline of a ten minute build is perfectly within reason." / "Since the secondary build may be much slower, it may not run after every commit."**【直】**（Fowler）+ **缺失证据**（Google 分钟数）置信度：高。
4. **「必需检查」标签本身不是强度**：skipped 与 neutral 都算通过，因此 true 强制力来自「是否存在无条件运行的检查 + 是否绑定可信 App + 是否禁止 admin 绕过」三项配置 —— [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) 原话："Required status checks must have a `successful`, `skipped`, or `neutral` status…"；"By default, the restrictions of a branch protection rule don't apply to people with admin permissions…"**【直】** 置信度：高。
5. **一手来源一致把覆盖门禁的落点放在「变更行」而非项目总量**：Google 给的门是 per-commit 99% 合理 / 90% 是下限，并明说项目级 >90% 多半不值得 —— [Google Testing Blog 2020-08](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)。**【半】** 置信度：高（引文一致性见第七节）。
6. **项目总量门就是 `fail_under` 的语义边界**：「If the total coverage measurement is under this value, then exit with a status code of 2」 —— [Coverage.py config](https://coverage.readthedocs.io/en/latest/config.html)；它对 patch 级回归不敏感：Cox 的同一手论文给出「改动基本未测而总量仍为 64.7%」的反例 —— [Differential coverage, arXiv:2008.07947](https://arxiv.org/abs/2008.07947)。**【直】**+**【半】** 置信度：高。
7. **总量阈值会把地板当天花板**：官方原文 "instead of treating 80% like a floor, engineers treat it like a ceiling" —— [SE@Google ch11](https://abseil.io/resources/swe-book/html/ch11.html)。**【直】** 置信度：高。
8. **覆盖率不是质量目标**：31,000 套测试、5 个最大 724k 行系统，结论是覆盖率「可用于识别测试不足的部分，但不应作为质量目标」；控制套件规模后相关性低到中等 —— [Inozemtseva & Holmes, ICSE 2014](https://cs.uwaterloo.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)；[Kochhar et al., IEEE TR 2017](https://inria.hal.science/hal-01653728/document) 在 100 个 Java 项目上报告项目级无显著相关。**【半】** 置信度：高（结论句）/ 中（具体系数）。
9. **厂商默认立场是「门新代码」**：Sonar 门禁条件可定义在 new code 或 overall code 上，且「In case of a pull request analysis, only the quality gate conditions applying to new code are used」；内置 Sonar way 的覆盖条件即「New code test coverage ≥ 80.0%」 —— [Understanding quality gates](https://docs.sonarsource.com/sonarqube-server/2026.2/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates)。**【直】** 置信度：高。
10. **变更行门有三种官方自陈的失效模式**：Sonar 在新行 <20 时忽略覆盖条件；diff-cover 需要 git、路径必须与 XML 报告匹配（不匹配即静默「No lines with coverage information」）、多行语句改动可能不被分析（`--expand-coverage-report`）；Codecov 明确「项目 72% 而 patch 0%」可以是同一次提交 —— [Sonar](https://docs.sonarsource.com/sonarqube-server/2026.2/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates)、[diff_cover](https://github.com/Bachmann1234/diff_cover)、[Codecov status checks](https://docs.codecov.com/docs/commit-status)。**【直】** 置信度：高。
11. **开启分支覆盖会改变阈值语义**：分母变为「每行 1 个 + 每个分支目的地 1 个」（`(covered_lines + covered_branches) / (num_statements + num_branches)`），报表数字与百分比会「对不上」，生成器表达式会误报 partial branch，且 3.12/3.13 的 `sysmon` 核心不支持分支覆盖 —— [coverage.py branch](https://coverage.readthedocs.io/en/latest/branch.html)、[FAQ](https://coverage.readthedocs.io/en/latest/faq.html)、[config](https://coverage.readthedocs.io/en/latest/config.html)。**【直】**；「同一条 80 在开关分支前后指向不同标准」为**【推】** 置信度：高。
12. **ratchet 不是任何官方工具的一等特性**：`fail_under` 配置项清单无 ratchet 类选项，Sonar 门条件是静态 error value，Codecov 只有 target/threshold；可核对的一手定义出自 Cox 的 ICST 2021（分类条件 UNC+UIC+LBC==0 实现「只升不降」），且同文自陈存在 "broken rachet" 效应 —— [config](https://coverage.readthedocs.io/en/latest/config.html)、[arXiv:2008.07947](https://arxiv.org/abs/2008.07947)。**【推】**（不存在）+ **【半】**（定义）置信度：中。
13. **变异测试的官方落点不是 score 门禁**：Google 自陈「在任何固定时间点计算绝对 mutation score 都昂贵到不可行」，走的是 per-diff 增量变异 + code review 中的 finding（72,425 diff / 1,159,723 变异体，75% 有反馈的发现被判有用）—— [State of Mutation Testing at Google](https://eecs481.org/readings/mutation-google.pdf)；工具侧同向：StrykerJS `thresholds` 默认 `{high:80, low:60, break:null}`，`break: null` 即「永不因 mutation score 让构建失败」 —— [StrykerJS configuration](https://stryker-mutator.io/docs/stryker-js/configuration/)。**【直】** 置信度：高。
14. **变异测试的噪音与分母必须先治理**：每 diff 存活变异体中位数 2 / P99 43，Google 的 arid 规则「是系统的关键部分」；等价变异体比例在真实项目间差两个数量级（0.4%–35%），且等价性判定不可判定 —— [Google 论文](https://eecs481.org/readings/mutation-google.pdf)、[ICSE 2014 Table 2](https://cs.uwaterloo.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)。**【直】** 置信度：高。
15. **断言密度不能当门禁**：一手论文明确「mandating that developers should have an assertion density of 30 asserts/KLOC may not lead to an effective use of assertions」；可机器化的只有**结构型**测试异味（tsDetect 19 条规则，含 Unknown Test / Redundant Assertion / Assertion Roulette，工具精度 P 96.01% / R 97.11%）—— [MSR-TR-2006-54](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr-2006-54.pdf)、[tsDetect ESEC/FSE 2020](https://testsmells.org/assets/publications/FSE2020_TechnicalPaper.pdf)。**【直】** 置信度：高。
16. **PBT 不是确定性信号**：`max_examples` 是名义值（失败时可能更少或更多）、失败用例会额外跑一次查 flakiness、输入分布是「deeply internal implementation detail」且随版本变化、示例数据库官方明确「不要依赖它保证测试正确性」—— [Hypothesis 官方文档源](https://hypothesis.readthedocs.io/en/latest/_sources/explanation/test-case-count.rst.txt)、[domain](https://hypothesis.readthedocs.io/en/latest/_sources/explanation/domain.rst.txt)、[replaying-failures](https://hypothesis.readthedocs.io/en/latest/_sources/tutorial/replaying-failures.rst.txt)。**【直】** 置信度：高。
17. **测试选择（TIA / 预测式）自带漏检预算且前置大型基础设施**：Meta 生产要求「预测 >95% 测试结果正确、对 >99.9% 的问题变更至少抓到一个失败测试」，同时只跑 1/3 相关测试（[Meta 工程博客](https://engineering.fb.com/2018/11/21/developer-tools/predictive-test-selection/)）；Google TAP 的省量（MinDist≤10 省 42% / ≤6 省 55%，且声称零漏检）来自**仿真**而非生产门禁，且作者明说拿不到 fault/coverage matrix（[TAP, ICSE-SEIP'17](https://huang.isis.vanderbilt.edu/cs8395/paper/google-testing-icse-seip-17.pdf)）。**【直】**；「非本仓规模解法」为**【推】** 置信度：高。
18. **能进门禁的机器化信号需同时满足三条**：判定确定性（无概率成分、不 flaky）、官方明确的失败语义/退出码、修复动作明确无需人工裁量。达标例：类型检查、架构边界、迁移漂移（`alembic check` 返回错误码或成功码，官方明说可接入 CI）、契约破坏性检查（oasdiff `breaking` 退出码 0/1）、依赖审计（pip-audit 退出码 0/1 且「cannot be suppressed」）、密钥扫描。不达标：mutation score、PTS、覆盖目标。**【推】**（综合各官方退出码语义） 置信度：中。
19. **工具默认与版本会漂移，阈值不可跨版本照搬**：mypy 官方警告 `--strict` 启用的开关集合「may change over time」；pyright 的 strict 覆盖「may only increase the strictness」；`--strict` 与 `typeCheckingMode` 的默认档不同 —— [mypy command_line](https://github.com/python/mypy/blob/master/docs/source/command_line.rst)、[pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)、[pyright getting-started](https://github.com/microsoft/pyright/blob/main/docs/getting-started.md)。**【直】** 置信度：高。
20. **提交前钩子不能作为唯一门禁**：客户端钩子「are **not** copied when you clone a repository」，`pre-commit` 退出非零可被 `--no-verify` 绕过；pre-commit 官方也要求同一配置在 CI 再跑一遍（`pre-commit run --all-files`），并把本地钩子的定位限定为「识别提交前的**简单问题**」 —— [Pro Git: Git Hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)、[pre-commit 官方](https://pre-commit.com/)。**【直】** 置信度：高。

## 二、门禁分层的最佳实践

分层判据（一手来源共同支持的三条，归纳为**【推】**）：(a) **反馈延迟成本由「谁在等」决定**（全体提交者 vs 单个发布者）；(b) **确定性**（fast/reliable vs slow/less deterministic）；(c) **副作用风险**（能否触达真实生产、配额、隐私）。依据：ch23 的 presubmit/postsubmit 分工与三条禁令 + Fowler 的两级构建。

| 层 | 放什么（含本仓映射） | 不放什么 | 时长与成本依据 |
|---|---|---|---|
| 提交前（本地钩子） | 秒级、可机械判定、可自动修复：本仓现有 merge-conflict / EOF / line-ending / ruff-check / ruff-format / 包边界 六项 | 测试、构建、任何需要网络或中间件的检查；**唯一例外**：防泄漏类（密钥扫描）可放，但必须先接受「首跑会慢」 | pre-commit 官方定位「识别提交前的简单问题，让评审专注架构」【直】；「The first time pre-commit runs on a file it will automatically download, install, and run the hook… may be slow」【直】 |
| PR（presubmit） | 快且可靠的正确性检查：本仓已有单元+契约、ruff、pyright(basic)、包边界、`contract-check`、`eval-retrieval`、gitleaks/pip-audit/pnpm audit、四镜像构建 | flaky 检查；直连真实生产后端；全仓测试；任何要数十分钟的端到端 | 「only fast, reliable ones」+「不跑全仓、只跑改动所在项目」+ flaky 成本由全体承担【直】；十分钟构建经验值【直】；长门禁诱发正式绕行开关（Chromium `No-Presubmit`/`No-Try`）与 admin 绕过【半】/【直】 |
| 合并（postsubmit） | 慢/不确定/需真依赖：本仓 `integration.yml`（真 PostgreSQL、全量、不许 skip 守卫）、迁移测试、E2E、`eval-answer` | 常驻红、无失效管理机制的检查 | presubmit 漏检必须被 postsubmit 接住并接受回滚；「there needs to be a mechanism to temporarily disable and keep track of them so that the release can go on」；且该清单必须治理，否则「a growing pile of disabled, old tests」【直】 |
| 发布 | 代表性验证（representative testing）+ 分级放量 + flag/回滚开关 | 穷尽验证；与生产不像的合成环境验收 | 「If _comprehensive_ testing is practically infeasible, aim for _representative_ testing instead.」/「Release qualification in a synthetic environment… can lead to late surprises.」/「we can simply switch the gatekeeper off rather than revert」【直】 |

两条跨层规则（一手）：**高层测试每次抓到 bug，都要回填一个低层测试**（[Fowler, Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html)）；**豁免金字塔的唯一条件是高层测试快、稳、易改**。另：DORA 官方口径是「速度与稳定性同向」，并主张从重量级变更审批转向同侪评审 + 自动化前置检测 —— [DORA 2019](https://dora.dev/research/2019/dora-report/)，即「多叠门禁换稳定」没有一手依据支撑【直】。

## 三、覆盖率门禁的选项矩阵

| 门对象 | 定义与官方出处 | 该门这类的依据 | 已知失效模式 | 适用条件 |
|---|---|---|---|---|
| 项目总量 | coverage.py `fail_under` 比较「the total coverage measurement」【直】 | 低成本、全局可判定；能形成长期纪律 | 对 patch 级回归不敏感（总量 64.7% 而改动基本未测）【半】；地板变天花板【直】；被大测试抬高（Google 建议只用 small 测试量覆盖率）【直】；作为质量目标被 I&H/Kochhar 否证【半】 | 存量债务小、或**仅作看板不阻断** |
| 变更行（patch / diff / delta） | Codecov `patch`：「only measures lines adjusted in the PR or single commit」【直】；diff-cover 官方定位「If you touch a line of code, that line should be covered」【直】；Google 的 changelist / delta coverage 定义【半】 | 最短可证伪判据；per-commit 99% 合理、90% 是下限【半】；官方把 changelist coverage 定位为「给全库覆盖低、存量债务多的团队」【半】 | 新行 <20 时门不触发（Sonar fudge factor）【直】；需 git 且路径必须匹配、多行语句可能漏【直】；同一次提交 patch 可 0% 而项目 72%【直】 | **有存量债务的成熟仓库**（本仓类型） |
| 新增代码（new code：时间窗/版本/参考分支） | Sonar：「New code is code that you've recently added or modified」；定义四选一【直】 | PR 分析下只应用 new code 条件；Sonar way 内置门 = 新增代码覆盖 ≥80%；动机是「不与存量整改纠缠」【直】 | 门对象本身会漂移（时间窗/基线可变）；`Specific analysis` 只能走 Web API、UI 不能配【直】；monorepo 多 flag 会产生无关 status、carryforward 默认不进 PR status【直】 | 需要覆盖服务且愿意长期维护 new-code 定义 |

行覆盖 vs 分支覆盖：

| 口径 | 分母构成 | 依据与代价 | 对门禁的含义 |
|---|---|---|---|
| 行覆盖（默认） | 每行 1 个执行机会 | Google ch11 的示例口径即行覆盖【直】 | 现成本最低、口径稳定；不区分「走了哪个分支」 |
| 分支覆盖（`branch = true`） | `(covered_lines + covered_branches) / (num_statements + num_branches)`【直】 | 能抓 partial branch；代价：报表数字与百分比「对不上」、生成器表达式误报、3.12/3.13 的 `sysmon` 不支持分支、需维护 `pragma: no branch` 清单【直】；更强覆盖（decision/MC-DC）未带来更多洞见【半】 | **同一数值在开关分支前后指向不同标准，历史基线不可跨模式比较**（【推】）；阈值必须重钉 |

**第三节结论：本仓该门「变更行（patch/diff）」这一类的覆盖率，项目总量降为看板；「新增代码（时间窗）」需引入覆盖服务，本仓无第二消费者，不上；分支覆盖不作为主门禁（若要观察，先只在 `medical-core` 打开并单独记录）。** 理由链：本仓 75.57% 总量已证明红色总量门不可维持（第六节必做 1）、口径换成变更行后阈值才与「你改的那行必须被测」对齐（Google per-commit 99%/90%）、且变更行门可**本地零服务**实现（diff-cover + coverage XML）。

## 四、覆盖率之外的强化项

| 项 | 一手依据要点 | 成本 | 适用规模 | 本仓结论 |
|---|---|---|---|---|
| 变异测试 **score 门禁** | Google 自陈全量 score 不可行；Stryker `break: null` 为默认；等价变异体 0.4%–35% 且不可判定【直】 | 极高（需为每个变异体重跑测试 + 噪音治理 + 分母语义决策） | 关键模块（支付/安全/协议）且已有增量基础设施 | **本仓不该上**（规模与安全等级不匹配；见第六节「明确不做」N1） |
| 变异测试 **per-diff 增量** | Google 模式 = covered ∩ not arid ∩ affected，每行至多 1 个变异体 + 最小测试集 + 反馈回路【直】 | 高（变异生成器、arid 规则、反馈回路） | 数千工程师级 monorepo | **本仓不该上**（前置设施成本远超收益） |
| 断言强度：**结构型测试异味扫描** | tsDetect 19 规则（无断言/重复断言/无消息）+ 工具精度 96%【直】 | 中（Python 侧无现成等价工具，需自写 AST 规则） | 有 LLM 生成测试流入的仓库 | **可选**（触发：出现第二例「有覆盖无断言」缺陷；形态优先自写 1 条 AST 检查，不引重工具） |
| 断言强度：**断言密度指标** | 一手论文明确反对按密度下指标；断言密度与缺陷密度相关只有 0.3 量级【直】 | 低（但会制造伪目标） | — | **本仓不该上** |
| Property-based testing（Hypothesis） | 执行次数不确定、分布跨版本可变、示例数据库不可依赖【直】 | 中（学习曲线 + 生成策略维护） | 有清晰不变量、纯函数密集的模块 | **可作写测试手段，不作门禁**（不作门禁的理由是确定性缺口；具体是否引入属测试策略决策） |
| 测试选择（TIA / 预测式 PTS） | Meta 生产要求含 ≤0.1% 漏检预算 + 训练数据治理；TAP 省量结论来自仿真【直】 | 极高（依赖图或 ML 训练管道） | 大型 monorepo、每次提交跑不完相关测试 | **本仓不该上** |
| 类型检查严格度 | pyright 官方 4 步渐进路径（CI 保持 type clean → 逐文件注解 → 逐目录 strict）；mypy `--strict` 子集「may change over time」【直】 | 中（修复量；升级可能突然变红） | 全部 | **渐进**（ADR 0080 已有计划；本仓 `basic`，见第五节） |
| 架构边界 / 迁移漂移 / 契约破坏 / 依赖审计 / 密钥扫描 | 各有官方退出码语义（`alembic check`、oasdiff `breaking`、pip-audit 0/1 不可抑制）【直】 | 低（多数已是配置一行） | 全部 | **已是或应成为机器信号**（本仓缺「契约破坏性检查」，见第五节） |

## 五、本仓现状与差距

| # | 项 | 现状 | 一手依据（本仓文件/字段） | 差距 | 结论性建议 |
|---|---|---|---|---|---|
| 1 | 覆盖率门禁总状态 | **红：总量 75.57%（4090 statements / 999 missed），且在 SQLite / 真 PostgreSQL × 带 / 不带 `-m` 四种组合下数字完全相同** | 实测输入；`pyproject.toml` `[tool.coverage.report] fail_under = 80`；`.github/workflows/ci.yml` python job `--cov --cov-report=term-missing` | 门禁不可被满足 → 长红门禁等价于无门禁（红即阻断的默认假设被绕行开关与 admin 绕过削弱【半】/【直】） | 必做 1：让门禁回到可判定状态。四种组合一致（【推】：说明该红色与执行后端、marker 过滤无关，不是环境伪影） |
| 2 | 门禁口径 | 只有**总量**一个阈值；**未开分支覆盖**（`[tool.coverage.run]` 无 `branch = true`）；**无 patch/变更行门禁**；**无覆盖率服务**（无 Codecov/Sonar/diff-cover）；**无 ratchet** | 根 `pyproject.toml` 全文（`[tool.coverage.run]` 仅 `source` + `omit`）；`ci.yml` 无第三方向覆盖服务步骤 | 与「门新代码/变更行」的一手共识方向相反：当前门的是存量总量 | 必做 2：PR 级加变更行覆盖门禁 |
| 3 | 门禁形态细节 | `addopts = "--strict-markers"` 已有；单元 job 已显式 `-m "not integration"`（注释直言「会静默 skip 后仍报绿（假门禁）」） | 根 `pyproject.toml` `[tool.pytest.ini_options]`；`ci.yml` python job | **无差距**（既有调研 `docs/research/ai-coding-tdd-best-practices.md` 第四节把这两项列为差距，与实测冲突，以实测为准，见第七节） | 保持；不要再为此加门禁 |
| 4 | 分辨率与语义 | `[tool.coverage.report]` 未设 `precision`；`skip_covered`/`skip_empty` 已开 | 根 `pyproject.toml` | 未设 `precision` 时非整数阈值的小数位无意义（coverage.py 官方：非整数值必须同时设 `precision`）【直】 | 与必做 1 同批处理（要么阈值取整，要么显式设 `precision`） |
| 5 | ADR 与实测不一致 | ADR 0080 记「pytest（覆盖率 ≥80%，基线 82%）」 | `docs/adr/0080-production-hardening-baseline.md` 决策 1；`docs/version-baseline.md` §1（`pytest-cov … fail_under=80`）与 §6 门禁 8 | 记录的基线（82%）与实测（75.57%）冲突 → 说明该门禁已红且无人处理 | 必做 3：同步文档与门禁数字，写清口径 |
| 6 | 提交前钩子 | 仅 6 项：merge-conflict、EOF、line-ending、ruff-check、ruff-format、包边界；**不含测试、不含密钥扫描** | `.pre-commit-config.yaml` 全文 | 密钥扫描只在 PR 级 CI（安全 job，gitleaks）→ 本地提交前无拦截 | 可选 1（触发：发生一次密钥误提交；依据：本地钩子不可分发、CI 才是强制点【直】） |
| 7 | 合并级门禁载体 | `integration.yml` 为合并级（`push: main` + `workflow_dispatch`），真 PostgreSQL 跑全量，并有「不许 skip」守卫（grep skipped 即失败） | `.github/workflows/integration.yml` 全文 | **无差距**，且比多数仓库更严（skip 即红） | 保持；这是「门禁可观测」的正例 |
| 8 | 分层与文档不一致 | `ci.yml` 的 `docker` job（四镜像 build）跑在 `pull_request` 上 | `ci.yml`（`on: pull_request` + docker job）；`AGENTS.md`「常用命令/测试与验收」把镜像构建列为**合并/发布**级；ADR 0080 决策 1 又把它写在 PR 级 | 三处声明不一致（ADR 0080 与 ci.yml 一致、AGENTS.md 不一致） | 必做 3 同批：统一措辞（ADR 0080 已是权威，改 AGENTS.md 一行即可） |
| 9 | 前端质量层 | `vitest.config.ts` 仅 `include: src/**/*.test.{ts,tsx}` + `environment: "node"`：**无覆盖率阈值**、无 jsdom；`check` = lint/typecheck/test:unit/build/fmt:check；Playwright 仅 chromium、`retries: 0`、`trace: retain-on-failure` | `apps/web/vitest.config.ts`、`apps/web/package.json`、`apps/web/playwright.config.ts`、`ci.yml` web job | 前端无覆盖率门禁；`retries: 0` 方向正确（不靠重试掩盖 flaky【直】） | 可选 2（触发条件见第六节；为覆盖率引 jsdom = YAGNI） |
| 10 | Python 类型严格度 | `[tool.pyright] typeCheckingMode = "basic"`，`include` 六个 src 包 | 根 `pyproject.toml`；ADR 0080 决策 2（basic 起步、逐步收紧、core 先行） | 与官方渐进路径一致（第 4 步「逐目录 strict」尚未开始） | 可选 3（触发：core 包有一批改动要一并收紧时） |
| 11 | 契约层 | 只有漂移门禁 `contract-check`（openapi-typescript `--check`）+ 导出脚本 | `ci.yml` web job；`apps/web/package.json` `contract-check`；AGENTS.md（ADR 0071） | 只要生成产物同步更新，破坏性变更（删字段/改必填/收窄类型）全绿（同 `docs/research/ai-coding-tdd-best-practices.md` 第四节） | 可选 4（oasdiff `breaking` 退出码 0/1 官方明确可接 CI【直】） |
| 12 | 供应与安全 | PR 级已跑 gitleaks（action 钉 commit SHA）+ pip-audit（`--strict`，注释说明 `--all-packages` 防「审计空文件恒绿」）+ `pnpm -r audit --prod` | `ci.yml` security job 全文 | **无差距**，且对 pip-audit 的假绿坑位有针对性处理 | 保持 |
| 13 | 规范载体 | `docs/development-standards.md` 全文无测试/覆盖率条款（测试与验收规则都在 `AGENTS.md`） | `docs/development-standards.md`（本次全文读取） | 覆盖率口径变更时没有「规范层」落点，容易只改配置不改文档 | 必做 3 的附带项：口径变更写进 ADR（结构上已有 `docs/adr/`），不必为此新增规范章节 |

## 六、建议方案

三档口径：**必做**=当前会产生错误信号或已失效的机制；**可选**=有明确触发条件再上；**明确不做**=已有充分理由不上（含「本仓不该上」项）。

### 必做

- **必做 1 —— 立即恢复覆盖率门禁的可判定性，并把总量降为看板。**
  改什么文件：根 `pyproject.toml`（`[tool.coverage.report]` 的 `fail_under` 调到可维持水位，或改为「总量不阻断、只打印」）+ 新 ADR 记录口径与水位。
  依赖是否新增：**否**。
  门禁时长影响：**无**（仅改判定）。
  依据强度：**高**（红门禁诱发绕行有官方绕行开关与 admin 绕过为证【半】/【直】；「80% 从地板变天花板」说明固定总量值本身会退化为天花板【直】）。实测水位 = 75.57%（4090/999）。
- **必做 2 —— PR 级新增「变更行覆盖率」门禁。**
  改什么文件：`ci.yml` python job（pytest 增 `--cov-report=xml`，随后 `diff-cover coverage.xml --fail-under=<值>`）；根 `pyproject.toml` dev group 增 `diff-cover`；新 ADR 记录阈值与例外。
  依赖是否新增：**是**（`diff-cover`，dev group；coverage.py / Sonar / Codecov 均无一等「变更行」能力，自写脚本成本更高）。
  门禁时长影响：**秒级**（读 XML + git diff，不重跑测试）。
  依据强度：**高**（Google per-commit 99%/90% 下限、diff-cover 官方定位、Sonar「PR 只应用 new code 条件」、Codecov patch 语义）。已知代价须写进 ADR：需 git 与路径匹配、多行语句改动可能漏（`--expand-coverage-report` 兜底）、新行过少时该门基本不触发（Sonar 的同类机制在新行 <20 时忽略覆盖条件）。
- **必做 3 —— 修正文档与实测的失真，并统一分层声明。**
  改什么文件：`docs/adr/0080-production-hardening-baseline.md`（基线 82% → 实测水位与口径）、`AGENTS.md`（镜像构建层级：合并/发布 vs `ci.yml` 的 PR 级，二者取一）、`docs/version-baseline.md` §1/§6（`fail_under` 与口径同步）。
  依赖是否新增：**否**。
  门禁时长影响：**无**。
  依据强度：**高**（本仓实测 + 文件对读；「文档门禁必须机器化」正是 ADR 0080 自身的决策目标）。

### 可选（注明触发条件与成本）

- **可选 1 —— 提交前加密钥扫描钩子。** 触发：发生一次密钥进入提交（哪怕随后改写历史）。改什么文件：`.pre-commit-config.yaml`。依赖：`gitleaks` 可执行（pre-commit repo 形式或 `language: system`）。时长：首跑会下载并因此变慢（pre-commit 官方明示【直】）。依据强度：中（CI 已在 PR 级拦，本地只是前移；且本地钩子不可分发【直】）。
- **可选 2 —— 前端覆盖率阈值。** 触发：前端出现第二类组件测试消费者，或同一类 UI 缺陷第二次绕过单测。改什么文件：`apps/web/vitest.config.ts`（`coverage.thresholds`）+ `package.json`。依赖：新增覆盖率提供者（如 `@vitest/coverage-v8`）。时长：单测耗时小幅上升。依据强度：中（vitest 原生支持阈值；`environment: node` 下先覆盖纯逻辑层，**不为此引入 jsdom**）。若上，优先用「未覆盖项上限」形态而非单纯百分比（贴合「找盲区」用途）。
- **可选 3 —— pyright 逐目录 strict（`medical-core` 先行）。** 触发：`medical-core` 有一批改动需要一并收紧类型时顺带落。改什么文件：根 `pyproject.toml` `[tool.pyright]`。依赖：否。时长：CI 秒级、修复量是真成本。依据强度：高（pyright 官方 4 步渐进即此形态；注意 strict 只许加严）。
- **可选 4 —— 契约破坏性变更门禁。** 触发：首次出现「生成产物同步更新但对外契约被破坏」并漏过评审。改什么文件：`ci.yml` web job。依赖：新增 `oasdiff`。时长：秒级。依据强度：高（退出码 0/1 官方明确「makes it easy to fail a CI step automatically」；`breaking` 只报破坏客户端项，不含纯文档改动）。
- **可选 5 —— 覆盖率 ratchet（只升不降）。** 触发：必做 2 落地且连续多次 PR 无回退后再评估。改什么文件：新脚本 + `ci.yml` 一步。依赖：自建（无官方一等支持【推】）。时长：秒级。依据强度：中（一手定义出自 Cox ICST 2021；同文自陈 broken ratchet 效应，落地须用分类条件而非裸百分比）。
- **可选 6 —— 单元层「无 I/O、无网络」机器强制 + a11y 自动跑入口。** 触发：出现第一例单测偷偷联网/读盘；a11y 因 WCAG 2.2 AA 是硬要求（`AGENTS.md`）可在下一次 UI 改动时顺带加一条 smoke。改什么文件：`pyproject.toml`（dev group）/`apps/web/playwright.config.ts`。依赖：禁网插件（如 pytest-socket）/`@axe-core/playwright`。时长：秒级~分钟级（E2E 在合并级）。依据强度：中（前者是缺失性证据，无实例不建；后者是仓库既有硬要求但无载体）。

### 明确不做（附理由）

- **N1 变异测试（mutation score）当门禁**：Google 自陈全量 score 不可行且找不到可执行呈现方式；Stryker 默认 `break: null`（即不让构建失败）；等价变异体 0.4%–35% 且判定不可判定；本仓规模（4090 statements）下「每个变异体重跑测试」的成本远高于其能给出的信号。
- **N2 预测式测试选择 / TIA**：需依赖图或 ML 训练管道，且官方把漏检写成预算（Meta ≤0.1% 问题变更可漏）；本仓 PR 规模远未到「跑不完相关测试」的程度。Google TAP 的省量结论来自仿真、且论文自陈无 fault/coverage matrix。
- **N3 断言密度指标 / 用例数 / 测试文件数当门禁**：一手论文明确反对按密度下指标；已有实测显示测试文件数会系统性高估验证强度（见 `docs/research/ai-coding-tdd-best-practices.md` 第三节第 6 条）。
- **N4 引入覆盖率服务（Codecov / SonarQube）**：本仓无第二消费者（对照 ADR 0071/0060 的 deletion test 口径），而 Codecov 的 monorepo 多 flag 与 carryforward 默认不进 PR status 反而是新增失效模式；变更行门禁可本地零服务实现（必做 2）。
- **N5 PBT（Hypothesis）当门禁**：官方文档明确 `max_examples` 不是确定执行次数、输入分布跨版本可变、示例数据库不可依赖 → 不满足「判定确定性」判据。（作为写测试手段不受此限。）
- **N6 开启分支覆盖并把现有 80 阈值平移过去**：分母语义改变（行 + 分支目的地），历史基线不可跨模式比较；还需维护 `pragma: no branch` 清单、处理生成器表达式误报、且 3.12/3.13 的 `sysmon` 核心不支持分支。若要看，先只在 `medical-core` 单独统计、不与总量阈值混用。
- **N7 追求「总量 ≥90%」或把总量阈值提到 80 以上**：一手来源明确项目级 >90% 多半不值得、90→95% 收益是对数级；且总量门会被大测试抬高（Google 建议只用 small 测试量覆盖率）。
- **N8 把集成/E2E 升到 PR 级**：官方分层原则是 presubmit 只放快且可靠者，且「真实生产后端不得在 presubmit 触碰」；本仓 `integration.yml` 已正确落在合并级，并带不许 skip 守卫。

## 七、未核实项与反方证据

**未核实项（含与草稿/既有文档的冲突，冲突一律以实测为准）**

1. **冲突（以实测为准）—— 既有调研的差距表已过期**：`docs/research/ai-coding-tdd-best-practices.md` 第四节把「无 `--strict-markers`」「集成靠静默 skip」列为差距；实测本仓 `pyproject.toml` 已有 `addopts = "--strict-markers"`，且 `ci.yml` 已显式 `-m "not integration"`。本文以实测为准。
2. **冲突（以实测为准）—— ADR 0080 的门禁数字失真**：ADR 记「覆盖率 ≥80%，基线 82%」，实测总量 75.57%。原因（何时开始红、是否有意放宽）无法从配置读出 → 未核实。
3. **冲突（以实测为准）—— 镜像构建的分层声明**：`ci.yml` 在 PR 级跑四镜像 build，`AGENTS.md` 把它写在合并/发布级，ADR 0080 又归 PR 级；三处不一致已实测确认，但「应以哪份为准」是文档决策，本文按 ADR 0080 归类。
4. **`testing.googleblog.com` 在本环境不可直连**：本文第一节第 5 条的 60/75/90 与 per-commit 99%/90% 引文来自搜索服务对原始 URL 的抽取（【半】）；与草稿 A（同样标【半】、日期 2020-08-07）、草稿 B（标直接证据）标注不一致，本文取更保守者【半】。
5. **机器化逐句核验不可用**：本环境下 `source_check` 返回 `missing-evidence`（既有调研已实测记录），因此本文所有【半】条目无机器校验，只有个人检索交叉比对。
6. **四种执行组合数字一致 → 红色与后端/过滤无关**：一致性本身是实测事实；「因此不是环境伪影」是**【推】**，未验证其它解释器/核心（如 3.13 / `sysmon`）下的差异。
7. **覆盖率 75.57% 的口径**：本仓未开分支，故该数字等同行覆盖；开启分支后总量公式不同，**不可与未来的分支数字直接比较**（【推】，依据 coverage.py 官方公式）。
8. **I&H ICSE 2014 / Zhang & Mesbah 2015 / Gopinath et al. ASE 2020 的结论句与相关系数**：PDF 直取失败，仅摘要或抽取级证据（草稿 A 未核实项 1–3）。
9. **Kochhar et al. TR 2017 的具体系数**（如「0.3% 变化」）：来源抽取存在跨栏拼接，句子不完整 → 不作为依据。
10. **Google 变异测试论文的算力成本**：论文只给「分钟级反馈」，无 CPU-hours / 每 diff 耗时 → 无法量化「变异测试门禁的成本」。
11. **`CI/门禁数量 ↔ 变更失败率` 的直接一手定量关系**：未找到（草稿 B 未核实项 7）；只有 DORA 的「速度与稳定性同向」相关性表述，且 DORA 数据是横断面。
12. **treat「覆盖率只升不降」的既有实例**：ratchet 在 coverage.py / Sonar / Codecov 官方能力清单中不存在（【推】，不能证明无隐藏实现）；第三方 ratchet 工具自述（jest-coverage-ratchet、CoverageRatchet）不能作为最佳实践依据。
13. **SonarQube `overall code` 覆盖率条件是否已弃用**：文档确认条件可定义在 overall code 上，但内置门是否仍含该条件未核实。
14. **Playwright / E2E 的官方数量配额**：官方未给出（缺失性证据），不得推论为「官方反对配额」。

**反方证据（与本文推荐冲突或限定其适用范围）**

1. **覆盖率不作为质量目标**：I&H 的结论句是「should not be used as a quality target because it is not a good indicator of test suite effectiveness」；同一手来源又指向 mutation score 作为候选替代 —— [ICSE 2014](https://cs.uwaterloo.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)。→ 对本文的限定：门禁主指标只能用于「定位未测的改动行」，不能当作质量结论；且不能声称有实证支持阈值本身。
2. **Google 自己不设全公司覆盖率阈值**：项目/项目组自选（Level 3 项目 60%/CL 70% … Level 5 项目 90%/CL 90%）—— [Code Coverage at Google, FSE 2019](https://homes.cs.washington.edu/~rjust/publ/google_coverage_fse_2019.pdf)。→ 任何「Google 要求 80%」的说法不成立。
3. **高覆盖仓库里覆盖门的增量收益被官方实证质疑**：changelist 覆盖率起点中位数已 >90%，且可视化覆盖率并未提高覆盖率 —— 同源。→ 对本仓的限定：必做 2 的收益主要来自「存量债大、总量低」这一前提（本仓 75.57%，前提成立）。
4. **「红灯即阻断」被官方机制削弱**：merge queue 明确允许「带失败检查的 PR 进组」以避免 flake 假阴性；GitHub 默认放行 admin 绕过；Chromium 有正式 `No-Presubmit`/`No-Try` —— [Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)、[About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[Chromium CQ](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/infra/cq.md)（【半】）。→ 长红门禁的现实后果是绕行，而非补测。
5. **反「全量测试进 presubmit」**：Google 明确「The main reason is that it’s too expensive」；Fowler 把慢测试移到次级构建、承认次级构建不随每次提交 —— 直接限定 N8 与「PR 级加更多检查」的边界。
6. **官方数据：红灯多为假**：84% 的 pass→fail 转变来自 flaky，只有 1.23% 的测试曾发现过 breakage —— [Micco, ICST 2017 keynote](https://www.aster.or.jp/conference/icst2017/program/jmicco-keynote.pdf)（【半】）。→ 门禁的可信度依赖 flaky 治理，而不是检查数量。
7. **反「用断言指标当门禁」**：Kudrjavets et al. 明确「We believe enforcing the use of assertions would not work well」，并建议若真要做密度，必须同时反查「新增断言是否覆盖了新代码」 —— [MSR-TR-2006-54](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr-2006-54.pdf)。
8. **PBT 的确定性缺口官方自认**：`max_examples` 名义值、分布跨版本可变、示例数据库不可依赖 —— 若有人主张「PBT 结果可复现」，此三句即反证。
9. **同形异义提醒（防混淆）**：Russ Cox 的 "Differential Coverage"（`research.swtch.com/diffcover`）是**调试**技术（比较成功/失败测试的覆盖率差异），与本文的差量覆盖率门禁无关（【半】）；引用时不得混用。
