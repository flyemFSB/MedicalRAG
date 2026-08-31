# 生产级测试系统最佳实践官方资料调研

> 调研日期：2026-08-01  
> 适用范围：MedicalRAG 单仓库；Python 3.14、uv、FastAPI、SQLAlchemy 2 async、Alembic、PostgreSQL 18、Redis、arq + 事务性 Outbox、Milvus dense+sparse/BM25 混合检索、Aegra + LangGraph、Langfuse；前端 Vite SPA + React + TypeScript + TanStack Query/Router + assistant-ui、pnpm + Turborepo、Vitest + Playwright；RAGAS 离线评测。  
> 来源约束：本文只引用技术项目自身维护的官方文档、官方项目仓库或标准组织文档；每条官方事实标注「已联网验证」（浏览器/CDP 或 WebFetch 实读原文）或「未联网验证」（退回训练知识，明确标注）。未使用博客、转载文章、营销材料或社区约定作为官方事实依据。  
> 文档性质：研究与实现前置约束，不包含可直接复制的实现代码，也不替代 `docs/spec.md`、`docs/architecture.md` 或 ADR。正文结论应结合 `docs/spec.md` 的 Testing Decisions、`docs/wayfinder/tickets/testing-quality-and-release-gates.md` 与既有调研文档（`devops-quality-security-and-observability.md`、`monorepo-best-practices.md`、`ragas-migration-and-ragent-evaluation.md`）使用。

## 1. 事实与设计建议的边界

本文使用以下标记（与既有调研文档一致）：

| 标记 | 含义 |
| --- | --- |
| **官方事实** | 上游官方文档或标准组织文档明确描述的语义、限制或推荐。 |
| **本项目建议** | 根据 MedicalRAG 已确认的职责、数据敏感性和部署约束推导出的落地方案，不是上游工具强制要求。 |
| **版本 caveat** | 版本、默认值、生命周期或稳定性可能变化，实施前需要再次核对并锁定。 |

如果“官方事实”和“本项目建议”发生冲突，事实用于理解工具边界，建议用于决定本项目的工程约束；改变建议时必须重新评估安全、测试、备份和发布影响。

## 2. API/契约测试

### 官方事实

**FastAPI 官方 Testing 文档：同步 TestClient 基于 Starlette + HTTPX**（已联网验证）
- https://fastapi.tiangolo.com/tutorial/testing/
- “Thanks to Starlette, testing FastAPI applications is easy and enjoyable. It is based on HTTPX…”（TestClient 基于 Starlette 与 HTTPX）；“the testing functions are normal def, not async def. And the calls to the client are also normal calls, not using await”（TestClient 测试是同步 def）。

**FastAPI 官方 Async Tests：异步测试不能用 TestClient，改用 httpx ASGI transport**（已联网验证）
- https://fastapi.tiangolo.com/advanced/async-tests/
- “The TestClient does some magic… But that magic doesn't work anymore when we're using it inside asynchronous functions.”（异步函数内 TestClient 的魔法失效）；官方做法是直接 `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` 搭配 `@pytest.mark.anyio`。
- “the AsyncClient won't trigger lifespan events… use LifespanManager from florimondmanca/asgi-lifespan”（async 方式不会触发 lifespan，需要 asgi-lifespan 自行管理）。

**Starlette 官方 TestClient：底层已切到 httpx2，普通 httpx 标记为 deprecated**（已联网验证，主代理抽查确认原文）
- https://www.starlette.io/testclient/
- 原文：“The TestClient is built on httpx2. Plain httpx is still supported, but deprecated - install httpx2 (included in starlette[full]) instead.”（这是 2026 年的变化，直接影响本项目测试依赖选型）；`raise_server_exceptions=False` 可用于测试返回 500 的响应；lifespan 需 `with` 上下文触发；backend 走 anyio（默认 asyncio，可用 uvloop）。
- **版本 caveat**：FastAPI 官方 Async Tests 文档当前仍按 `httpx`（非 httpx2）的 `AsyncClient(transport=ASGITransport(...))` 编写；实现前需核对 FastAPI/httpx/httpx2 的最新关系，锁定测试用 HTTP 客户端版本。

**schemathesis：基于 OpenAPI/GraphQL schema 的属性测试工具**（已联网验证）
- https://schemathesis.readthedocs.io/en/stable/ 、 https://github.com/schemathesis/schemathesis
- “Schemathesis automatically generates property-based tests from your OpenAPI or GraphQL schema and exercises the edge cases that break your API.”
- 其解决的契约问题原文：“Schema violations where your API returns different data than documented”、“Validation bypasses where invalid data gets accepted”、“Integration failures when responses don't match client expectations”。pytest 用法 `@schema.parametrize()` + `case.call_and_validate()`。

**openapi-spec-validator：OpenAPI 规范静态合规校验**（已联网验证）
- https://github.com/python-openapi/openapi-spec-validator
- “validates OpenAPI Specs against the OpenAPI 2.0/3.0/3.1/3.2 specification… aims to check for full compliance”；提供 CLI、pre-commit hook 与 Python 包。

**openapi-diff：OpenAPI 3.x 规格差异比较（breaking-change 检测）**（已联网验证）
- https://github.com/OpenAPITools/openapi-diff
- “Compare two OpenAPI specifications (3.x) and render the difference…”；CI 门禁参数 `--fail-on-incompatible` / `--fail-on-changed` / `--state`（Java 工具，可用 Docker 运行）。

**openapi-typescript：从 OpenAPI schema 生成 TypeScript 类型**（已联网验证）
- https://github.com/openapi-ts/openapi-typescript
- “Generate TypeScript types from static OpenAPI schemas”，配套 openapi-fetch 用生成类型做类型化请求。

### 本项目建议

- 简单端点测试默认用同步 `TestClient`；涉及异步数据库/异步 fixture 的断言改用 `httpx.AsyncClient` + `ASGITransport` + `@pytest.mark.anyio`，并显式管理 lifespan（asgi-lifespan）。不要在异步测试函数里用 TestClient。
- 契约分层（对应 ADR 0071 OpenAPI single-source contract generation）：
  1. `openapi-spec-validator` 在 CI 静态校验 OpenAPI 3.1 规范本身（可挂 pre-commit）；
  2. `schemathesis` 做 schema 驱动的属性/契约测试（抓契约违规、校验绕过、500 边界）——它是契约符合性测试，不是业务功能测试的替代；
  3. `openapi-diff` 作为 breaking-change 门禁（`--fail-on-incompatible`）；
  4. `openapi-typescript` 生成前端 TS 类型，使前端请求层与后端合同绑定，并在 CI 检查生成结果无未提交差异。
- 契约测试只验证“API 与 OpenAPI 文档一致”，医疗领域规则、权限、证据链等业务行为仍由功能/集成/E2E 层覆盖。

## 3. 队列/后台任务测试

### 官方事实

**arq 官方文档：没有独立 Testing 章节，但若干 API 官方注明测试用途**（已联网验证）
- https://arq-docs.helpmanual.io/ （当前 v0.28.0；全文标题检索无 Testing 章节）
  - `Worker.async_run()` — “Asynchronously run the worker, does not close connections. **Useful when testing.**”
  - `Worker.run_check()` — “Run async_run(), check for failed jobs and raise `arq.worker.FailedJobs` if any jobs have failed”（失败即抛异常，天然断言）。
  - `ArqRedis.queued_jobs()` — “Get information about queued, **mostly useful when testing.**”
- retry 语义：`raise Retry(defer=ctx['job_try']*5)` 递增退避；“after max_tries (default 5) the job will permanently fail”；worker 关闭时 `task.cancel()` 抛 `CancelledError`，job 会重跑（pessimistic execution，至少一次）。Worker 默认 `job_timeout=300s`、`max_tries=5`、`retry_jobs=True`、`max_jobs=10`。

**arq 官方仓库：官方测试模式 = Testcontainers Redis + burst Worker fixture**（已联网验证）
- https://github.com/python-arq/arq （原 samuelcolvin/arq 已迁移，URL 重定向）
- tests/conftest.py 使用 `RedisContainer('redis:latest')`（Testcontainers）+ `Worker(functions=…, burst=True, poll_delay=0, max_jobs=10)` fixture，每个用例 `flushall` 隔离。这是官方自己跑测试的实际模式。

**Python asyncio 官方：后台 fire-and-forget 任务必须持有引用**（已联网验证）
- https://docs.python.org/3/library/asyncio-task.html
- `create_task` 警告：“Save a reference to the result of this function, to avoid a task disappearing mid-execution. The event loop only keeps weak references to tasks… may get garbage collected at any time”（后台任务应保存引用，建议用 set + add_done_callback 或 TaskGroup）。

**Transactional Outbox 模式官方定义**（已联网验证）
- https://microservices.io/patterns/data/transactional-outbox.html
- “first store the message in the database as part of the transaction that updates the business entities. A separate process then sends the messages…”；保证 “Messages are guaranteed to be sent **if and only if** the database transaction commits”；已知缺陷 “The Message relay might publish a message more than once… a message consumer must be idempotent”。

### 本项目建议

- Worker 测试：Testcontainers Redis + `burst=True`/`poll_delay=0` 的 Worker fixture，用 `run_check()` 断言无 `FailedJobs`；每个用例 flushall 隔离；不依赖常驻 worker 进程。
- Retry 测试：用 `Retry(defer=ctx['job_try']*…)` 断言退避步进与 `max_tries` 上限；用短 `job_timeout` 触发超时路径。断言“重试耗尽 → 终态失败 + 可重放”与票据中 failure injection 一致。
- Outbox 测试：核心不变量是“业务事务提交 ⇔ 消息可见”（事务回滚则无消息）；relay 重复投递不产生重复副作用（消费者幂等），对应 ADR 0063 与票据中的 outbox relay crash → re-scan/re-deliver。
- 后台任务：测试里保存 task 引用或用 TaskGroup；隔离事件循环（asyncio_mode + loop scope 见下节），防止跨 loop 引用泄漏。

## 4. 前端测试

### 官方事实

**Vitest**（均 已联网验证）
- Projects（monorepo）：https://vitest.dev/guide/projects — “This feature is also known as a workspace. The workspace is deprecated since 3.2 and replaced with the projects configuration.”（monorepo 用 `test.projects` 定义各包隔离配置）。
- setupFiles：https://vitest.dev/config/setupfiles — “Paths to setup files… They will run before each test file in the same process.”
- retry（原生）：https://vitest.dev/config/retry — “Retry the test specific number of times if it fails… Default: 0. CLI: --retry <times>”（支持 `{count, delay, condition}`）。
- mocking：https://vitest.dev/guide/mocking — “Always remember to clear or restore mocks before or after each test run.”（vi.fn / vi.spyOn / vi.mock，需要 reset）。
- 并行/分片：https://vitest.dev/guide/features — “Run tests on different machines using --shard and --reporter=blob… --merge-reports”；watch 模式默认本地、CI 下自动 run 模式。

**Testing Library**（均 已联网验证）
- https://testing-library.com/docs/react-testing-library/intro — “querying the DOM in the same way the user would”；`data-testid` 是 “escape hatch”（兜底，不是首选）。
- Queries：https://testing-library.com/docs/queries/about — “getByRole… should be your top preference for just about everything.”（查询优先级 Role > LabelText；findBy 带默认 1000ms 重试）。
- user-event vs fireEvent：https://testing-library.com/docs/user-event/intro — “fireEvent dispatches DOM events, whereas user-event simulates full interactions… This is why you should use user-event to test interaction with your components.”；https://testing-library.com/docs/dom-testing-library/api-events — “Most projects have a few use cases for fireEvent, but the majority of the time you should probably use @testing-library/user-event.”
- act 警告：https://testing-library.com/docs/react-testing-library/faq — “This warning is usually caused by an async operation causing an update after the test has already finished.”；解法用 find*/waitFor 等待或 mock 异步，其中 find*/waitFor “better matches the expectations of a user”。

**Playwright**（均 已联网验证）
- 并行：https://playwright.dev/docs/test-parallel — “By default, test files are run in parallel. Tests in a single file are run in order, in the same worker process.”；`fullyParallel: true` 开启文件内并行；workers 可写 `'50%'`。（旧 URL `test-parallelism` 已 404，以新路径为准）
- CI 建议：https://playwright.dev/docs/ci — “We recommend setting workers to '1' in CI environments to prioritize stability and reproducibility.”，官方示例 `workers: process.env.CI ? 1 : undefined`。
- retries：https://playwright.dev/docs/test-retries — “By default failing tests are not retried.”；重试成功的测试标记为 “flaky”；运行时可用 `testInfo.retry` 检测。
- 配置示例：https://playwright.dev/docs/test-configuration — 官方示例配置含 “retries: process.env.CI ? 2 : 0” 与 `forbidOnly: !!process.env.CI`（“CI 上 retries=2”以示例配置形式存在，非单独建议段）。
- sharding：https://playwright.dev/docs/test-sharding — `--shard=x/y`；“recommended to use fullyParallel: true when aiming for balanced distribution across shards”；blob reporter + `merge-reports` 合并分片报告。
- trace：https://playwright.dev/docs/trace-viewer — “Traces should be run on continuous integration on the first retry of a failed test by setting the trace: 'on-first-retry'.”
- 可访问性：https://playwright.dev/docs/accessibility-testing — **Playwright 无内置自动 a11y 扫描**，官方示例用 `@axe-core/playwright`；官方免责声明：“Automated accessibility tests can detect some common accessibility problems… But many accessibility problems can only be discovered through manual testing. We recommend using a combination of automated testing, manual accessibility assessments, and inclusive user testing.”

**axe-core / Turborepo**（均 已联网验证）
- https://github.com/dequelabs/axe-core README — “With axe-core, you can find on average 57% of WCAG issues automatically.”；无法自动判定者返回 “incomplete” 需人工复核。（官方现表述为 **57%**，不是流传的“约 30%”）
- https://turborepo.com/docs/crafting-your-repository/caching — “Turborepo will restore the results of your task from cache using a fingerprint… Turborepo assumes that your tasks are deterministic.”（测试任务缓存依赖 inputs→hash 的确定性）。

### 本项目建议

- 分层：Vitest `test.projects`（monorepo 各包独立配置，替代旧 workspace）；`setupFiles` 统一注入 jest-dom、MSW、matchMedia 等；组件测试与 E2E 分属不同入口，E2E 不放默认 turbo run。
- 组件测试查询按官方优先级 `getByRole` > `getByLabelText` > `getByText`；交互一律 `user-event`；异步用 `findBy*`/`waitFor` 避免 act 警告；对“应不存在”的内容用 `queryBy*` 断言。
- Playwright E2E CI 基线：`workers: 1`（或稳定后分 shard）、`retries: process.env.CI ? 2 : 0`、`forbidOnly: !!process.env.CI`、`trace: 'on-first-retry'`；shard 时 `fullyParallel: true` + blob + merge-reports。
- 可访问性：Playwright 侧接 `@axe-core/playwright`，tags 用 wcag2a/wcag2aa；自动化只覆盖部分问题（axe 官方 57%），必须配套人工走查（结合 Accessibility Insights for Web）覆盖键盘流、焦点、朗读器路径；与票据“automated scans + manual review”一致。
- flaky 管理：Playwright retries + flaky 标记 + trace 定位；Vitest 可用 `--retry.count` 兜底单元层；E2E 层不与 GHA 自动重试叠加（GHA 无此能力，见下节）。
- Turborepo：只有确定性测试任务才能进缓存；不稳定测试考虑对该 task 关闭缓存。

## 5. CI 与质量门禁

### 官方事实

**GitHub Actions：并行/矩阵/并发**（已联网验证）
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- “By default, GitHub will maximize the number of jobs run in parallel depending on runner availability.”；矩阵上限 “A matrix will generate a maximum of 256 jobs per workflow run.”；“The default behavior of GitHub Actions is to allow multiple jobs or workflow runs to run concurrently.”
- concurrency：官方原文 “Use concurrency to ensure that only a single job or workflow using the same concurrency group will run at a time.”，配 `cancel-in-progress: true` 取消进行中运行；`queue` 属性 single（默认）/ max:100。

**GitHub Actions：依赖缓存与 fork 安全**（已联网验证）
- https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- “On a cache miss, the action automatically creates a new cache if the job completes successfully.”（仅 job 成功后写缓存）；“You cannot change the contents of an existing cache.”
- fork 安全：原文 “only these workflow triggers can create or overwrite caches in the default branch's scope: push, workflow_dispatch, repository_dispatch, delete, registry_package, page_build, schedule”。`pull_request_target`、`issue_comment`、`workflow_run` 等低信任触发对 default branch 缓存只读，防 cache poisoning。

**GitHub Actions：services 容器（每 job 全新、自动销毁）**（已联网验证）
- https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers
- “GitHub creates a fresh Docker container for each service configured in the workflow, and destroys the service container when the job completes.”；限制：容器/服务只支持 Linux runner。

**Testcontainers / 容器内测试**（已联网验证）
- https://java.testcontainers.org/supported_docker_environment/ 、 https://java.testcontainers.org/continuous_integration/dind_patterns/
- “To run Testcontainers-based tests, you need a Docker-API compatible container runtime.”；“Testcontainers itself can be used from inside a container.”（sibling 模式：挂载 docker.sock）；“While Docker-in-Docker (DinD) is generally considered an instrument of last resort, it is necessary for some CI environments.”

**Docker 官方 CI**（已联网验证）
- https://docs.docker.com/build/ci/ — “Containers are reproducible, isolated environments that yield predictable results.”（容器=可复现隔离环境，测试结果可预测）。

**覆盖率作为门禁**（已联网验证）
- pytest-cov：https://pytest-cov.readthedocs.io/en/latest/config.html — “--cov-fail-under MIN: Fail if the total coverage is less than MIN.”
- coverage.py：https://coverage.readthedocs.io/en/latest/config.html — “[report] fail_under: If the total coverage measurement is under this value, then exit with a status code of 2.”
- Codecov：https://docs.codecov.com/docs/commit-status — “Useful for blocking Pull Requests that don't meet a particular coverage threshold.” project 状态对比整体 vs base；patch 状态只测 PR 新增行；`informational: false` 时作为门禁。

**分支保护 / required status checks**（已联网验证）
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- “If you use branch protection rules that require specific status checks, make sure that job names are unique across all workflows.”（job 名须全仓唯一，否则状态歧义）；“Required status checks must have a successful, skipped, or neutral status before collaborators can make changes to a protected branch.”；strict（默认，要求 up-to-date）vs loose。

**flaky 处理：GHA 无自动重试，插件/框架层有**（已联网验证）
- GHA：https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs — “Re-runs use the privileges of the actor who initially triggered the workflow.”，重跑上限 50 次。（官方没有 job 级自动 retry 功能）
- Playwright：https://playwright.dev/docs/test-retries — “Test retries are a way to automatically re-run a test when it fails.”
- pytest-rerunfailures：https://pypi.org/project/pytest-rerunfailures/ — “pytest plugin to re-run tests to eliminate flaky failures”，v16.4 支持 Python 3.14。

**uv / pnpm 官方 CI 集成**（均 已联网验证）
- uv：https://docs.astral.sh/uv/guides/integration/github/ — “we recommend the official astral-sh/setup-uv action, which installs uv, adds it to PATH, (optionally) persists the cache”；`enable-cache: true` 内置缓存；“It is considered best practice to pin to a specific uv version.”；安装命令 `uv sync --locked --all-extras --dev`；`uv cache prune --ci`（“optimized for CI”）。
- pnpm：https://pnpm.io/continuous-integration — 官方配置 `pnpm/action-setup` + `actions/setup-node` with `cache: "pnpm"`；“Only cache pnpm's store and cache directories in locations writable by trusted jobs.”（fork 安全）；“When pnpm detects that it is running in CI, it switches to frozen-lockfile mode automatically.”

### 本项目建议

- 拓扑：单 workflow 多 job；后端 test job 可 matrix（Python 3.14 单版本即可）；所有 job 名保持全仓唯一（required status checks 要求）。
- 并发：`concurrency: group: ${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`。
- 依赖：`astral-sh/setup-uv@v8`（固定版本 + `enable-cache: true`）→ `uv sync --locked --all-extras --dev` → 测后 `uv cache prune --ci`；前端 `pnpm/action-setup` + `setup-node(cache: "pnpm")`；缓存 key 由 setup-uv 依据 uv.lock 自动处理；pnpm 缓存遵循官方 fork 安全指引。
- 服务隔离：PostgreSQL/Redis 集成测试可用 GHA `services:`（每 job 全新、自动销毁）；Milvus 较重且无现成 GHA service 镜像 → 用 Testcontainers 起，或 Docker job + 挂 docker.sock（sibling 模式），避免 DinD。统一 ubuntu-latest。
- 覆盖率门禁：单测 job 内 `pytest --cov --cov-fail-under=<阈值>`（或 coverage.py 配置 fail_under，低于则 exit 2）；或上传 Codecov 并开 project/patch status，两者取一作为 required status check。建议用 patch（只测 PR 新增行）防整体阈值被存量代码“稀释”失效。
- 分支保护：main 开启 required status checks（lint / typecheck / backend-test / frontend-test / coverage），strict 模式。
- flaky：后端 `pytest-rerunfailures`（`--reruns 2`，仅对显式标记的用例）；E2E Playwright `retries: 2`（CI）；GHA 层不做自动重试（官方无此能力），靠手动 Re-run failed jobs + 对连续 flaky 计数告警。

## 6. 测试金字塔与覆盖率

### 官方事实

**pytest 官方 Good Integration Practices：src layout + importlib import mode**（已联网验证）
- https://docs.pytest.org/en/stable/explanation/goodpractices.html （旧地址 `good_practices.html` 已 404）
- 原句：tests 目录放在被测包之外、“strongly suggested to use a src layout”、“use importlib import mode”；给 tests 加 `__init__.py` 会使 pytest 把仓库根加入 `sys.path`，被测包从源码而非安装包导入（在 tox 等场景出错）。

**pytest fixtures / mark**（均 已联网验证）
- https://docs.pytest.org/en/stable/how-to/fixtures.html — conftest.py 供多 module 共享 fixture；scope 可选 function/class/module/package/session，默认 function。
- https://docs.pytest.org/en/stable/how-to/mark.html — 在 `[tool.pytest.ini_options] markers=[...]` 注册 mark 免告警；`strict_markers` 下未注册即报错。

**pytest-xdist 并行**（已联网验证）
- https://pytest-xdist.readthedocs.io/en/latest/ — `-n auto` 按 CPU 数起 worker；`--dist load`（默认）/loadscope/loadgroup/worksteal；“Each worker is responsible for performing a full test collection”，worker 是独立进程。

**覆盖率：pytest-cov / coverage.py**（均 已联网验证）
- https://pytest-cov.readthedocs.io/ — “`--cov-fail-under MIN`: Fail if the total coverage is less than MIN”、`--cov-branch` 分支覆盖；coverage.py 侧 `[report] fail_under` 低于阈值 exit status 2。
- https://coverage.readthedocs.io/en/latest/branch.html — `coverage run --branch` 跟踪 “where a line … could jump to more than one next line”。
- 覆盖率≠质量：https://coverage.readthedocs.io/en/latest/faq.html — “It's good, but it isn't perfect.”（官方对“覆盖率不能代表质量”的表述）。

**变异测试：mutmut**（已联网验证）
- https://github.com/boxed/mutmut — “Mutation testing is a way to be reasonably certain your code actually tests the full behavior … you might have 100% code coverage but you won't survive mutation testing”。
- pytest 官方文档没有变异测试章节，仅在插件列表中提及 pytest-gremlins。

### 本项目建议

- Python 采用包外 `tests/` + `src` layout + importlib import mode（与既有 monorepo 研究一致）；在 pyproject 注册全部自定义 marker（`integration`、`contract`、`eval`、`flaky` 等）并启用 `strict_markers`。
- 覆盖率阈值用 pytest-cov `--cov-fail-under` + `--cov-branch` 落地；行覆盖率只做下限门禁，行为质量靠关键路径测试 + 变异测试兜底（mutmut 需要 fork/WSL，Windows 上运行受限，宜只在 Linux CI 跑少量核心模块）。
- 测试金字塔分层（与票据一致）：unit（medical-core 规则/状态机/策略 + 内存适配器，不碰外部服务）→ contract（FastAPI/事件包络/Agent Protocol）→ integration（Compose test profile）→ E2E（Playwright）；不要用 E2E 替代大量 unit tests。

## 7. 异步与数据库测试

### 官方事实

**pytest-asyncio：asyncio_mode 与 fixture 模式**（已联网验证；当前 1.4.0，2026-05-26）
- https://pytest-asyncio.readthedocs.io/en/latest/
- 默认 `asyncio_mode=strict`，纯 asyncio 项目官方推荐 auto（文档原文 “is the recommended default”）；异步 fixture 须用 `@pytest_asyncio.fixture`（0.25+ strict 模式下普通 `@pytest.fixture` 配异步函数会告警）；0.24 引入 `loop_scope` / `asyncio_default_fixture_loop_scope`，1.0 移除了 `event_loop` fixture；默认每个测试独立事件循环，官方称为 “highest level of isolation”。

**SQLAlchemy 2.0 async：跨事件循环共享 engine 必须 NullPool**（已联网验证）
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- “If the same engine must be shared between different loop, it should be configured to disable pooling using NullPool”；基准写法 `create_async_engine` + `async_sessionmaker(expire_on_commit=False)` + 结束 `await engine.dispose()`。
- 事务回滚包装模式（begin → begin_nested → rollback）：当前 2.0.51 官方文档已无 “Testing with asyncio Extensions” 一节，该模式无官方一手原文，属社区广泛实践——**未联网验证（训练知识）**，实现前需以仓库自建模式为准。

**Testcontainers for Python 2.0.0：Postgres/Redis 官方用法**（已联网验证）
- https://testcontainers-python.readthedocs.io/
- `PostgresContainer("postgres:16").get_connection_url()`、`RedisContainer().get_client()`、安装 `pip install testcontainers[postgres]`；前置条件是 Docker-API 兼容运行时（容器内需挂 `/var/run/docker.sock` 或 `DOCKER_HOST`）。官方文档没有 pytest fixture/scope 专用页。

**xdist 与数据库隔离**（已联网验证）
- https://pytest-xdist.readthedocs.io/en/latest/how-to.html — session 级 fixture 在多 worker 下会执行多次，“pytest-xdist does not have a builtin support for ensuring a session-scoped fixture is executed exactly once, this can be achieved by using a lock file”；`-n0` 时 worker_id 返回 “master”。

### 本项目建议

- pytest 配置 `asyncio_mode = "auto"` + 异步 fixture 一律 `@pytest_asyncio.fixture`；unit 层保持每测试独立事件循环的默认隔离；集成层显式控制 loop scope。
- 数据库测试模式：`async_sessionmaker(expire_on_commit=False)`；需要“事务回滚”隔离时采用 begin/begin_nested/rollback 包装（实现时按仓库实测验证，当前官方无一手章节）；跨 loop 共享 engine 必须 `NullPool`，teardown 调 `engine.dispose()`。与 spec.md “persistence tests 用 SQLite + PostgreSQL（可选 integration profile）” 对齐。
- Testcontainers：PostgreSQL/Redis 集成测试用 `PostgresContainer`/`RedisContainer`，需要 Docker；更重拓扑（Milvus、MinIO、Aegra）走 Compose `test` profile（与票据一致）。
- 并行隔离：xdist 多 worker 时每个 worker 独立数据库 schema 或独立容器，或用文件锁保证 session 级 fixture 只初始化一次；不要把 session 级 DB 种子当作跨 worker 共享。

## 8. AI/RAG 测试与评测

### 官方事实

**LangGraph 官方图测试：每测试新建 checkpointer 实例实现状态隔离**（已联网验证）
- https://docs.langchain.com/oss/python/langgraph/test
- 官方原句 “create your graph before each test… compile it within tests with a new checkpointer instance”（每测试用新 checkpointer 实例编译实现状态隔离）；`graph.nodes["x"].invoke()` 可单点测节点；`update_state(values, as_node=…)` + `invoke(None, interrupt_after=…)` 做局部执行。

**LangGraph 官方 time travel / replay / fork**（已联网验证）
- https://docs.langchain.com/oss/python/langgraph/use-time-travel
- “Replay: Retry from a prior checkpoint. Fork: Branch from a prior checkpoint with modified state”；用 `get_state_history` + `invoke` 重放；“update_state does not roll back… branches from the specified point”。

**LangGraph 官方 interrupts（HITL 测试）与故障容错**（均 已联网验证）
- https://docs.langchain.com/oss/python/langgraph/interrupts — 用 `Command(resume=…)` 恢复被中断的执行；中断值经 `stream.interrupts`/`interrupted` 观测。
- https://docs.langchain.com/oss/python/langgraph/fault-tolerance — `add_node(retry_policy=RetryPolicy(max_attempts=3))`；“retry_on” 默认排除 ValueError/TypeError/OSError，HTTP 仅 5xx；“Only after retries are exhausted does the error handler run”；错误码含 `GRAPH_RECURSION_LIMIT`。

**LangGraph CLI：没有 `langgraph test` 命令**（已联网验证）
- LangSmith CLI 仅有 dev/build/deploy/up/dockerfile 等命令；不存在 InputSchema/StateSchema/Expect 测试子命令。

**RAGAS（当前 v0.4.3）指标与自定义 judge**（均 已联网验证）
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ — Faithfulness “measures how factually consistent a response is with the retrieved context”；Answer Relevancy 生成人工问题 + embedding 余弦相似度；Context Precision = precision@k；Context Recall 按 claims 拆解。
- https://docs.ragas.io/en/stable/howtos/customizations/customize_models/ — “Both of these models can be customised”（`llm_factory`/`embedding_factory`）；指标继承 `MetricWithLLM`，评分前需设 LLM 对象，如 `FactualCorrectness(llm=evaluation_llm)`；旧的 `metrics.llm=` 仍兼容但 `LangchainLLMWrapper` 已弃用。
- https://docs.ragas.io/en/stable/getstarted/rag_testset_generation/ — `TestsetGenerator(llm=, embedding_model=)`、`generate_with_langchain_docs(docs, testset_size=10)`；0.4 为知识图谱 + QuerySynthesizer 场景生成。
- 可信度：metrics overview 载 “LLM-based metrics… can be somewhat non-deterministic… shown to be more accurate and closer to human evaluation”；`RunConfig(seed=42)` 用于复现。
- 迁移：https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/ — “v0.4 replaces the evaluate() function with an experiment()-based approach”；`evaluate(metrics=[…])` 在 0.4 标记弃用、v1.0 移除。当前仓库中不存在 `LLMScenario`/`LLMTest`/`Judge` 抽象（与训练知识中“1.x 新抽象”不一致，以本次实测为准）。

**LangChain 官方 mock LLM vs 真实调用**（均 已联网验证）
- https://docs.langchain.com/oss/python/langchain/test/unit-testing — “By replacing the real LLM with an in-memory fake… tests are fast, free, and repeatable without API keys”；推荐 `GenericFakeChatModel`；`FakeListLLM(responses=[…])` 位于 `langchain_core.language_models.fake`。
- https://docs.langchain.com/oss/python/langchain/test/integration-testing — LLM 输出非确定，官方建议 “Assert on structure, not content”；用 `pytest.mark.integration` 分离；支持 record-and-replay HTTP。
- `langchain_core.caches` 只有 `BaseCache` + `InMemoryCache`，官方定位为省钱提速，不是测试复现手段。

**Langfuse 官方评测与 LLM-as-a-Judge**（已联网验证）
- https://langfuse.com/docs/evaluation/… — 官方定义 LLM-as-a-Judge 并提供托管 evaluator（Hallucination、Context-Relevance 等）；离线用 `run_experiment(name, data, task, evaluators=[…])`；CI/CD 用 GitHub Action `langfuse/experiment-action`，以抛 `RegressionError` 作为门禁。

**OpenAI 官方 evals**（已联网验证）
- https://platform.openai.com/docs/guides/evals — “Writing evals… is an essential component to building reliable applications”；平台 Evals/Graders 于 2026-10-31 只读、2026-11-30 关停（自身依赖方需迁移）；graders 返回 0–1 分数，`score_model` 支持 seed/temperature。

### 本项目建议

- 图测试（pytest）：每个测试用新的 checkpointer 实例（InMemorySaver 或 Langfuse checkpoint backend）编译 graph；`update_state` + `interrupt_after` 测局部路径；`get_state_history` + `update_state` 做故障重放与 fork；`Command(resume=…)` 模拟 human-in-the-loop；关键节点配 `RetryPolicy` 白名单（只重试可安全重试的异常类型）。
- Mock 分层：单元层用 `FakeListLLM`/`GenericFakeChatModel`（含工具调用与错误注入）；集成层才真实调用，断言“结构而非内容”，用 marker 分开跑；官方缓存机制不作测试复现手段。
- 评测（RAGAS v0.4.3）：用 `llm_factory` 注入 judge LLM；`RunConfig(seed=42)` 提升复现性；指标取 Faithfulness、Context Precision/Recall、Answer Relevancy；迁移到 `experiment()` 而不是被弃用的 `evaluate()`；评测集用 `TestsetGenerator` 生成 + 脱敏/合成数据（结合既有 ragas 调研：医疗场景任何 LLM-as-judge 分数都不能作为临床安全门禁）。
- 观测与回归：Langfuse CallbackHandler 全链路 trace + 生产侧 observation evaluator；CI 用 `run_experiment` + LLM-as-Judge，`RegressionError` 作门禁（对应 ADR 0059/0062 Langfuse 观测基线）。
- **版本 caveat**：RAGAS 0.4 正在向 experiment() 迁移，v1.0 会移除 evaluate()；本建议基于 2026-08-01 实测的 v0.4.3，实现前锁定版本并重新核对迁移页。

## 9. 安全与可观测测试

### 官方事实

**OWASP WSTG：安全测试贯穿全生命周期，反对事后黑盒**（已联网验证）
- 项目页 https://owasp.org/www-project-web-security-testing-guide/ ，框架正文 https://raw.githubusercontent.com/OWASP/wstg/master/document/3-The_OWASP_Testing_Framework/0-The_Web_Security_Testing_Framework.md
- 原文：“To improve the security of applications, the security quality of the software must be improved. That means testing security during the definition, design, development, deployment, and maintenance stages, and not relying on the costly strategy of waiting until code is completely built.”
- 结构：框架分 Phase 1–5（开发前/定义与设计/开发/部署/运维）；技术测试章 12 类：信息收集、配置与部署管理、身份管理、认证、授权、会话管理、输入验证、错误处理、弱密码、业务逻辑、客户端、API 测试。Phase 5.3 要求“每次变更部署后复查安全未受影响并纳入变更管理”。

**OWASP ASVS v5.0：验证等级与“自动化≠跑现成工具”**（已联网验证）
- 正文 https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/en/0x03-What-is-the-ASVS.md 、0x04-Assessment_and_Certification.md
- 三级：L1 “minimum requirements… around 20% of the ASVS requirements”；L2 “Most applications should be striving to achieve this level… around 50%”；L3 “final ~30%… defense-in-depth”。按风险敏感度选级。
- 原文：“The ASVS is designed to be highly testable… By building unit and integration tests that test and fuzz for specific and relevant abuse cases… it should be easier to check that these controls are operating correctly on each build.”
- 0x04：“When automated security testing tools such as DAST and SAST are correctly implemented in the build pipeline, they may be able to identify some security issues…”；以及 “In summary, testable using automation != running an off the shelf tool.”；“It is strongly encouraged to perform documentation or source code-led (hybrid) penetration testing”。

**OWASP SAMM：Security Testing 成熟度 M1→M3**（已联网验证）
- https://owaspsamm.org/model/verification/security-testing/
- M1 “Perform security testing (both manual and tool based) to discover security defects.”；M2 “…through automation complemented with regular manual security penetration tests.”；M3 “Embed security testing as part of the development and deployment processes.”

**OWASP API Security Top 10 2023：测试失败不得部署**（已联网验证）
- https://owasp.org/API-Security/ 、API1 https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- API1 How To Prevent 原文：“Write tests to evaluate the vulnerability of the authorization mechanism. Do not deploy changes that make the tests fail.”

**OWASP Top 10 for LLM Applications 2025**（已联网验证）
- https://genai.owasp.org/llm-top-10/
- 官方结构：LLM01 Prompt Injection / 02 Sensitive Information Disclosure / 03 Supply Chain / 04 Data and Model Poisoning / 05 Improper Output Handling / 06 Excessive Agency / 07 System Prompt Leakage / 08 Vector and Embedding Weaknesses / 09 Misinformation / 10 Unbounded Consumption。
- 测试相关原文：LLM01 “Conduct adversarial testing and attack simulations… Perform regular penetration testing and breach simulations, treating the model as an untrusted user”；LLM04 “Test model robustness with red team campaigns”；LLM06 “Use SAST and DAST, IAST in development pipelines”；LLM08（RAG）“…… should be monitored and evaluated”。
- OWASP GenAI Red Team Handbook（官方仓库同目录）：目标 “test, probe, and evaluate the safety and security of LLM applications”，官方示例用 garak 与 promptfoo 做自动化红队/回归。

**Langfuse 官方评测（在线 LLM-as-judge + 离线 experiment 门禁）**（已联网验证）
- 总览 https://langfuse.com/docs/evaluation/overview — “Evals give you a repeatable check of your LLM application's behavior… catch regressions before you ship a change.”；“It happens both online, on live production traces, and offline, before you ship a change.”
- LLM-as-judge https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge — “an LLM is used to assess the quality of outputs produced by another LLM application…”；“Observation-level evaluators are the recommended target for live production data; trace-level evaluators are deprecated.”
- Datasets https://langfuse.com/docs/evaluation/experiments/datasets — “A dataset is a collection of inputs and expected outputs and is used to test your application.”；可从生产 trace 抽取测试用例。
- CI/CD https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd — “Use Langfuse experiments in your CI/CD pipeline to catch quality regressions before they ship.”；越阈值抛 `RegressionError`，GitHub Actions 用 `langfuse/experiment-action` 作门禁。
- Code evaluators：官方定位为确定性/客观检查，与 LLM-as-judge 互补。

**OpenTelemetry GenAI 语义约定（实验性）**（已联网验证）
- 规范已从 https://opentelemetry.io/docs/specs/semconv/gen-ai/ 整体迁移至 https://github.com/open-telemetry/semantic-conventions-genai ，状态为 Development（实验性）。
- `gen_ai.*` 属性：`gen_ai.operation.name`、`gen_ai.provider.name`（由 `gen_ai.system` 更名）、`gen_ai.request.model`、`gen_ai.response.id`、`gen_ai.usage.input_tokens/output_tokens` 等；span name SHOULD be “{gen_ai.operation.name} {gen_ai.request.model}”。

### 本项目建议

- 分层安全测试：以 WSTG 12 类作为功能安全测试清单；以 ASVS 作为验证等级目标（医疗数据敏感，目标 L2/L3，对应票据“认证/所有权/请求校验/上传限制/出站与脱敏”信任边界项）；落实“自动化≠跑现成工具”——SAST/DAST 进 CI + 按 ASVS 条目写应用专属单元/集成测试 + 白盒/灰盒渗透。
- 成熟度路线：按 SAMM Security Testing M1→M3 演进；以 API Top 10 “测试失败不得部署”为安全门禁原则。
- LLM 安全测试：按 LLM Top 10 2025 逐条映射测试用例（RAG 重点 LLM02 敏感信息泄露、04 数据/模型投毒、05 输出处理、07 系统提示词泄露、08 向量/嵌入弱点）；LLM01 红队/对抗测试常态化；garak/promptfoo 自动化扫描可作 CI 环节。
- LLM 可观测性测试：用 Langfuse 官方体系——在线 LLM-as-judge 监控生产 trace（observation 级 evaluator，trace 级已弃用）+ 离线 datasets/experiments 回归门禁（`RegressionError`）；code evaluators 做确定性检查；OTel `gen_ai.*` 为实验性，采集层标注其风险。与 ADR 0059/0062/0072（Langfuse fail-open、唯一 AI/RAG trace 后端、可选自托管）对齐。
- **版本 caveat**：Langfuse eval 真实路径为 `langfuse.com/docs/evaluation/...`（`docs.langfuse.com/evaluation/llm-as-a-judge` 等旧路径 404）；OTel gen-ai 规范整体迁移到独立仓库；实施前锁定 Langfuse 版本并核对文档路径。

## 10. 总体结论

### 10.1 测试类型是否齐全（对照 `testing-quality-and-release-gates` 票据的 10 类）

| 类型 | 结论 | 依据（本文） |
| --- | --- | --- |
| 单元测试 | 齐全 | pytest src layout + importlib + markers；asyncio_mode=auto + `@pytest_asyncio.fixture`；LLM 用 `FakeListLLM`/`GenericFakeChatModel`；LangGraph 每测试新建 checkpointer；医疗规则用内存适配器 |
| 契约测试 | 齐全 | FastAPI 同步 TestClient + 异步 `ASGITransport`；schemathesis 属性测试；openapi-spec-validator；openapi-diff 门禁；openapi-typescript 前端类型绑定 |
| 集成测试 | 齐全 | Testcontainers（Postgres/Redis）+ GHA `services:` 或 Compose `test` profile；arq burst Worker + `run_check()`；outbox“事务提交⇔消息可见”不变量 |
| 端到端测试 | 齐全 | Playwright `workers=1`(CI)、`retries=2`、`trace: on-first-retry`、sharding + blob/merge-reports |
| 检索评测 | 齐全 | `eval-retrieval` per PR（ID-based 指标 + MRR/nDCG 等，既有 ragas 调研）；`eval-answer`（RAGAS experiment()）nightly/release |
| 安全测试 | 齐全 | WSTG 12 类清单；ASVS L2/L3 目标；API Top 10“测试失败不得部署”；LLM Top 10 逐条映射 + 红队/garak/promptfoo |
| 可访问性 | 齐全 | `@axe-core/playwright`（wcag2a/aa）+ 人工走查（axe 自动只覆盖约 57%） |
| 迁移测试 | 齐全 | Alembic 空库建表；索引重建与 Active Index Version cutover（既有票据） |
| 可观测性测试 | 齐全 | Langfuse 在线 LLM-as-judge（observation 级）+ 离线 datasets/experiments + `RegressionError` 门禁；OTel `gen_ai.*` 标注实验性 |
| 故障注入 | 齐全 | arq `RetryPolicy`/`Retry(defer=…)`、worker 关闭 `CancelledError` 重跑语义、outbox relay 幂等（票据 + 本文 §3） |

### 10.2 覆盖范围是否完整有效

- **完整**：测试金字塔分层（unit→contract→integration→E2E）有官方一手依据且无层级缺位；异步/数据库、队列/outbox、AI/RAG、前端、CI、安全与可观测八个维度均获得官方事实支撑，每个维度已映射到 MedicalRAG 具体工具与配置。
- **有效**的关键做法：契约测试只验“API 与 OpenAPI 一致”，业务行为仍由功能/集成/E2E 覆盖；覆盖率用 `fail_under` + `--cov-branch` 做下限、patch 级别防稀释，不把总百分比当质量承诺；LLM 层“单测 mock、集成断言结构、评测用 seeded judge”；Langfuse observation 级 evaluator 是生产推荐目标；安全上落实“自动化≠跑现成工具”。

### 10.3 缺口与实现前必须落地的决策

1. **SQLAlchemy async 事务回滚隔离模式无官方一手章节**（当前 2.0.51 文档无 “Testing with asyncio Extensions”）——本文标注「未联网验证（训练知识）」，实现阶段必须在仓库内固化一套 begin/begin_nested/rollback（或每 worker 独立 schema）实测模式并写成测试文档。
2. **RAGAS v0.4 → experiment() 迁移窗口**：`evaluate()` 在 0.4 弃用、v1.0 移除；需锁定 v0.4.x，实现时按迁移页核对。judge LLM 校准（align-llm-as-judge）、中文验证与种子数据仍需项目级落地。
3. **httpx2 vs httpx 选型**：Starlette TestClient 已切换 httpx2 并弃用普通 httpx，但 FastAPI Async Tests 文档仍按 httpx 编写；依赖锁定阶段必须定夺测试 HTTP 客户端版本。
4. **变异测试平台限制**：mutmut 在 Windows 受 fork/WSL 限制，只在 Linux CI 对核心模块（medical-core 规则/状态机）运行，不做全仓门禁。
5. **医疗安全边界**：任何 LLM-as-judge / RAGAS 分数不能作为临床安全门禁（既有 ragas 调研结论），只作离线诊断与回归信号；临床安全审查保持专家驱动。
6. **URL/版本漂移**：Langfuse eval 真实路径、OTel gen-ai 仓库迁移、WSTG/ASVS 当前版本、pytest-asyncio 1.x 移除 `event_loop` 等，实施前按本文标注的版本 caveat 逐一核对锁定。
7. **CI 基础设施**：Milvus 无现成 GHA service 镜像，需在 Testcontainers 与 Docker sibling 模式（挂 docker.sock，避免 DinD）间定夺。

### 10.4 质量门禁 checklist（落地顺序）

- [ ] 每次提交：Ruff + 类型检查 + 快速 unit tests（`--cov-branch` + `--cov-fail-under=<阈值>`）
- [ ] Pull Request：+ 契约测试（spec-validator / schemathesis / openapi-diff）+ `eval-retrieval` + Vitest unit/component + concurrency（cancel-in-progress）+ coverage patch 状态
- [ ] 合并/发布：Compose `test` profile 集成测试 + Alembic 迁移测试 + Playwright E2E（`workers=1`/shard + retries）+ `eval-answer`（RAGAS experiment()）+ Langfuse experiment `RegressionError` + 镜像构建
- [ ] 分支保护：main 上 required status checks（job 名全仓唯一，strict 模式）
- [ ] flaky：pytest-rerunfailures（仅显式标记用例）+ Playwright retries + 手动 Re-run + 连续 flaky 计数告警（GHA 无自动重试）

## 11. 官方一手来源

所有链接均为官方文档、官方项目页面或标准组织文档；访问/验证日期为 2026-08-01。

### pytest / 覆盖率 / 变异测试

- [PY1] [pytest — Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [PY2] [pytest — How to use fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [PY3] [pytest — How to mark test functions](https://docs.pytest.org/en/stable/how-to/mark.html)
- [PY4] [pytest-xdist — 官方文档](https://pytest-xdist.readthedocs.io/en/latest/)
- [PY5] [pytest-xdist — How-to（session fixture 与 DB 隔离）](https://pytest-xdist.readthedocs.io/en/latest/how-to.html)
- [PY6] [pytest-cov — 官方文档（--cov-fail-under / --cov-branch）](https://pytest-cov.readthedocs.io/)
- [PY7] [coverage.py — Branch coverage](https://coverage.readthedocs.io/en/latest/branch.html)
- [PY8] [coverage.py — FAQ（覆盖率≠质量）](https://coverage.readthedocs.io/en/latest/faq.html)
- [PY9] [coverage.py — Configuration（fail_under exit 2）](https://coverage.readthedocs.io/en/latest/config.html)
- [PY10] [mutmut — 官方仓库](https://github.com/boxed/mutmut)
- [PY11] [pytest-rerunfailures — PyPI](https://pypi.org/project/pytest-rerunfailures/)

### 异步与数据库测试

- [ASY1] [pytest-asyncio — 官方文档](https://pytest-asyncio.readthedocs.io/en/latest/)
- [SQL1] [SQLAlchemy 2.0 — Asyncio 扩展（NullPool / dispose）](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [TC1] [Testcontainers for Python — 官方文档](https://testcontainers-python.readthedocs.io/)
- [TC2] [Testcontainers — Supported Docker environment](https://java.testcontainers.org/supported_docker_environment/)
- [TC3] [Testcontainers — Continuous Integration / DinD patterns](https://java.testcontainers.org/continuous_integration/dind_patterns/)

### API/契约测试

- [FA1] [FastAPI — Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [FA2] [FastAPI — Async Tests（ASGITransport + anyio）](https://fastapi.tiangolo.com/advanced/async-tests/)
- [ST1] [Starlette — TestClient（httpx2 说明）](https://www.starlette.io/testclient/)
- [SCH1] [schemathesis — 官方文档](https://schemathesis.readthedocs.io/en/stable/)
- [SCH2] [schemathesis — GitHub 仓库](https://github.com/schemathesis/schemathesis)
- [OSV1] [openapi-spec-validator — GitHub 仓库](https://github.com/python-openapi/openapi-spec-validator)
- [OD1] [openapi-diff — GitHub 仓库（OpenAPITools）](https://github.com/OpenAPITools/openapi-diff)
- [OT1] [openapi-typescript — GitHub 仓库](https://github.com/openapi-ts/openapi-typescript)

### 队列/后台任务

- [ARQ1] [arq — 官方文档](https://arq-docs.helpmanual.io/)
- [ARQ2] [arq — GitHub 仓库（官方测试模式）](https://github.com/python-arq/arq)
- [ASY2] [Python asyncio — Task / create_task 引用说明](https://docs.python.org/3/library/asyncio-task.html)
- [OUT1] [microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)

### AI/RAG 测试与评测

- [LG1] [LangGraph — Testing（官方）](https://docs.langchain.com/oss/python/langgraph/test)
- [LG2] [LangGraph — Time Travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- [LG3] [LangGraph — Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LG4] [LangGraph — Fault Tolerance（RetryPolicy）](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [LC1] [LangChain — Unit Testing（FakeListLLM 等）](https://docs.langchain.com/oss/python/langchain/test/unit-testing)
- [LC2] [LangChain — Integration Testing](https://docs.langchain.com/oss/python/langchain/test/integration-testing)
- [RG1] [RAGAS — Available Metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [RG2] [RAGAS — Customize Models（llm_factory / MetricWithLLM）](https://docs.ragas.io/en/stable/howtos/customizations/customize_models/)
- [RG3] [RAGAS — Testset Generation](https://docs.ragas.io/en/stable/getstarted/rag_testset_generation/)
- [RG4] [RAGAS — Migrate from v0.3 to v0.4（experiment()）](https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/)
- [OAI1] [OpenAI — Evals（官方指南）](https://platform.openai.com/docs/guides/evals)

### 前端测试

- [VI1] [Vitest — Test Projects（workspace 已弃用）](https://vitest.dev/guide/projects)
- [VI2] [Vitest — Setup Files](https://vitest.dev/config/setupfiles)
- [VI3] [Vitest — Retry](https://vitest.dev/config/retry)
- [VI4] [Vitest — Mocking](https://vitest.dev/guide/mocking)
- [VI5] [Vitest — Features（--shard / blob / merge-reports）](https://vitest.dev/guide/features)
- [TL1] [Testing Library — React 简介（user 视角查询）](https://testing-library.com/docs/react-testing-library/intro)
- [TL2] [Testing Library — Queries（getByRole 优先级）](https://testing-library.com/docs/queries/about)
- [TL3] [Testing Library — user-event](https://testing-library.com/docs/user-event/intro)
- [TL4] [Testing Library — DOM Events（fireEvent 适用场景）](https://testing-library.com/docs/dom-testing-library/api-events)
- [TL5] [Testing Library — React FAQ（act 警告）](https://testing-library.com/docs/react-testing-library/faq)
- [PW1] [Playwright — Test Parallelism](https://playwright.dev/docs/test-parallel)
- [PW2] [Playwright — Continuous Integration（workers=1）](https://playwright.dev/docs/ci)
- [PW3] [Playwright — Test Retries](https://playwright.dev/docs/test-retries)
- [PW4] [Playwright — Test Configuration（retries 示例）](https://playwright.dev/docs/test-configuration)
- [PW5] [Playwright — Test Sharding](https://playwright.dev/docs/test-sharding)
- [PW6] [Playwright — Trace Viewer（on-first-retry）](https://playwright.dev/docs/trace-viewer)
- [PW7] [Playwright — Accessibility Testing（@axe-core/playwright）](https://playwright.dev/docs/accessibility-testing)
- [AX1] [axe-core — GitHub 仓库（57% WCAG 自动覆盖）](https://github.com/dequelabs/axe-core)
- [TB1] [Turborepo — Caching（任务确定性）](https://turborepo.com/docs/crafting-your-repository/caching)

### CI 与质量门禁

- [GH1] [GitHub Actions — Workflow syntax（并行/矩阵/concurrency）](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GH2] [GitHub Actions — Dependency caching（fork 安全）](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GH3] [GitHub Actions — Docker service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers)
- [GH4] [GitHub Actions — Re-run workflows and jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [GH5] [GitHub — About protected branches（required status checks）](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [CV1] [Codecov — Commit status（project/patch 门禁）](https://docs.codecov.com/docs/commit-status)
- [DOC1] [Docker Docs — CI 构建（容器=可复现隔离）](https://docs.docker.com/build/ci/)
- [UV1] [uv — Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)
- [PN1] [pnpm — Continuous Integration](https://pnpm.io/continuous-integration)

### 安全与可观测

- [W1] [OWASP WSTG — 项目页](https://owasp.org/www-project-web-security-testing-guide/)
- [W2] [OWASP WSTG — 测试框架正文（贯穿全阶段）](https://raw.githubusercontent.com/OWASP/wstg/master/document/3-The_OWASP_Testing_Framework/0-The_Web_Security_Testing_Framework.md)
- [A1] [OWASP ASVS — What is the ASVS（L1–L3）](https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/en/0x03-What-is-the-ASVS.md)
- [A2] [OWASP ASVS — Assessment and Certification（自动化≠跑现成工具）](https://raw.githubusercontent.com/OWASP/ASVS/master/5.0/en/0x04-Assessment_and_Certification.md)
- [S1] [OWASP SAMM — Security Testing](https://owaspsamm.org/model/verification/security-testing/)
- [S2] [OWASP SAMM — Verification](https://owaspsamm.org/model/verification/)
- [AP1] [OWASP API Security Top 10 2023](https://owasp.org/API-Security/)
- [AP2] [OWASP API1 — Broken Object Level Authorization（测试失败不得部署）](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [L1] [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/)
- [LF1] [Langfuse — Evaluation Overview](https://langfuse.com/docs/evaluation/overview)
- [LF2] [Langfuse — LLM-as-a-Judge（observation 级推荐）](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [LF3] [Langfuse — Datasets](https://langfuse.com/docs/evaluation/experiments/datasets)
- [LF4] [Langfuse — Experiments in CI/CD（RegressionError）](https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd)
- [OTG1] [OpenTelemetry — GenAI semantic conventions（实验性，已迁移仓库）](https://github.com/open-telemetry/semantic-conventions-genai)
