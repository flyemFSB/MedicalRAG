# 测试体系调研（对标主流开源项目）

- 日期：2026-09-13
- 性质：规划期调研底稿，服务于「测试体系重构方案」；结论只在被方案/ADR 引用时生效
- 方法：全部结论对照一手来源（官方文档、GitHub 仓库源码/CI 配置）核实；标注未能核实项

## 一、对标对象与核实来源

| 对象 | 类型 | 核实方式 |
|---|---|---|
| langchain-ai/langchain（libs/core） | uv 多包 monorepo | GitHub API 读 `libs/core` 目录树与 `pyproject.toml` 全文 |
| fastapi/full-stack-fastapi-template | FastAPI 全栈模板 | GitHub API 读 `backend/`、`backend/pyproject.toml`、`.github/workflows/test-backend.yml`、`.github/workflows/playwright.yml` |
| Playwright 官方文档 | E2E 框架 | 抓取 [best-practices](https://playwright.dev/docs/best-practices)、[auth](https://playwright.dev/docs/auth) |
| Vitest 官方文档 | 前端单测 | 抓取 [guide/coverage](https://vitest.dev/guide/coverage) |
| MSW 官方文档 | 网络 mock | 抓取 [mswjs.io/docs](https://mswjs.io/docs/)（2.x） |
| schemathesis | OpenAPI 契约测试 | 抓取 [官方文档](https://schemathesis.readthedocs.io/en/stable/) |
| oasdiff | OpenAPI 破坏性变更门禁 | 抓取 [GitHub](https://github.com/oasdiff/oasdiff) |
| testcontainers-python | 容器化集成测试 | GitHub API 读 README |
| calcom/cal.com | 大型 TS monorepo | GitHub API 读仓库根目录与 `apps/web` 目录树 |
| danny-avila/LibreChat | 开源聊天应用（TS monorepo） | GitHub API 读仓库根目录、`api/`、`e2e/` 目录树 |

## 二、逐项发现

### 1. langchain（Python 多包 monorepo 标杆）

- 目录约定：每个包 `tests/` 下分 `unit_tests/` 与 `integration_tests/` 两个子目录（`libs/core/tests/` 实测目录树）；仓库无根级 tests，测试随包走。
- pytest 配置（`libs/core/pyproject.toml` 实测）：
  - `addopts = "--snapshot-warn-unused --strict-markers --strict-config --durations=5"`——未知 marker 直接报错、报最慢测试；
  - `asyncio_mode = "auto"`（与本仓相同）；
  - marker 只声明真正用于选择运行的（`requires`、`compile`），分层靠目录而非 marker 数量。
- 测试依赖清单（实测）：`freezegun`（时间冻结）、`pytest-mock`、`syrupy`（快照）、`responses`（HTTP mock）、**`pytest-socket`（单元测试禁网，防 fake 不彻底偷联网）**、`pytest-xdist`（并行）、`blockbuster`（检测 async 测试里的阻塞调用）、`pytest-benchmark`。
- 分层运行：单测与集成测试分开调用（unit_tests 全量跑在每次 CI；integration_tests 按 provider 甄别运行）。
- `tests/**` 在 ruff `per-file-ignores` 里放宽文档字符串/魔法值/断言类规则——测试代码用生产 lint 标准会误伤。

### 2. fastapi/full-stack-fastapi-template（官方全栈模板）

- 测试布局：`backend/tests/{api,crud,scripts,utils}` + 顶层 `conftest.py`（实测目录树）；测试按「API 路由 / CRUD / 脚本」分层组织。
- **DB 测试在 PR CI 直接跑**（`test-backend.yml` 实测）：`docker compose up -d --wait db mailpit` → 迁移 → pytest（真 Postgres，不是 SQLite 替身）→ `coverage report --fail-under=90`。`--wait` 等容器健康再跑。
- E2E 也在 PR 级（`playwright.yml` 实测）：**4 个 shard 并行**（`strategy.matrix` + `--shard=i/4`）、`--fail-on-flaky-tests --trace=retain-on-failure`、blob report 上传后 `playwright merge-reports` 合并 HTML、`alls-green` 汇总 job 供分支保护引用、`changes` job 按路径过滤避免无关 PR 白跑。
- 三方 action 全部钉 full commit SHA（与本仓 gitleaks 同做法）。
- 工作流按层拆文件：`test-backend.yml` / `playwright.yml` / `test-docker-compose.yml` / `pre-commit.yml`，各自触发与缓存策略独立。

### 3. Playwright 官方文档

- [best-practices](https://playwright.dev/docs/best-practices)：测用户可见行为而非实现细节；locator 优先 `getByRole` 等面向用户的查询；web-first 断言（`expect.poll`/`expect().toPass()`）；**CI 失败重试 + trace viewer 定位**；每个 PR 都要跑 E2E；**测试间彻底隔离（每个测试独立登录态，不共享）**。
- [auth](https://playwright.dev/docs/auth)：**storageState 复用登录态**——用一个 setup project 先登录、把会话写入 `storageState` 文件（放 `.gitignore` 目录如 `playwright/.auth/`），后续测试 `test.use({ storageState })` 直接带会话跑；服务端会话型登录要在每次登录前重置状态；多角色（普通用户/operator）各自保存一份 storageState。

### 4. Vitest 官方文档

- [coverage](https://vitest.dev/guide/coverage)：`@vitest/coverage-v8`（快，无需插桩）或 istanbul；`coverage.include`/`exclude` 圈定范围；`coverage.thresholds` 支持全局与按文件阈值（lines/functions/branches/statements），超限即失败；`all: true` 把零测试文件也计入分母。

### 5. MSW（Mock Service Worker）

- [docs](https://mswjs.io/docs/)（2.x）：同一份 handler 定义同时服务浏览器与 Node（Vitest 组件测试共用）；请求拦截在网络层，代码零侵入；支持 SSE/事件流 mock（对聊天流式场景有意义）；与 OpenAPI 结合做 schema-first handler 类型化是社区主流用法。

### 6. schemathesis

- [官方文档](https://schemathesis.readthedocs.io/en/stable/)：从 OpenAPI schema 自动生成 property-based 测试，覆盖「schema 声明 vs 实际响应」一致性与 5xx/异常输入；可作 pytest 插件或 CLI 跑，能挂进 CI 门禁。

### 7. oasdiff

- [GitHub](https://github.com/oasdiff/oasdiff)：对 OpenAPI diff 检测**破坏性变更**（删字段/改必填/收窄类型等），支持 `breaking` 命令对比 git 基线（`oasdiff breaking base:<branch>`），非零退出码即门禁失败；提供 GitHub Action 与 CI 集成说明。

### 8. testcontainers-python

- README 实测：`with PostgresContainer("postgres:16") as postgres:` 在 pytest 内编程式起容器、自动生成连接串。定位是「无需预置 compose 的临时容器」；与 docker compose 相比：省编排文件但每次冷启动容器更慢、需要 Docker-in-CI 权限相同。
- 结论：**与 compose profile 二选一即可，本项目已选 compose（ADR 0080 第 9 条），无需引入**。

### 9. cal.com（TS monorepo）

- 仓库根目录实测：`vitest.workspace.ts` + `vitest.config.mts` + `setupVitest.ts` + `vitest-mocks/`（集中 mock 目录）+ 根级 `playwright.config.ts` + `apps/web/playwright/`（E2E spec 专目录）+ `__checks__/` + `checkly.config.ts`（生产环境可用性监控，测试外溢到运行时）。
- 单元测试与组件同目录共存（如 `apps/web/proxy.test.ts`），E2E 独立目录。

### 10. LibreChat（开源聊天应用，TS monorepo）

- `api/`（Express）用 jest，`api/test/` 专目录（实测）；`packages/` 分包（api/client/data-provider/data-schemas）。
- `e2e/` 实测目录：**十几个 playwright 配置文件按场景拆分**——`playwright.config.ts`（主）、`a11y.ts`（**无障碍专跑**）、`lighthouse.ts`、`mock.ts`（mock 模式 E2E）、`real.ts`（真实后端）、`redis.ts`、多个性能/基准配置，外加 `fixtures/`、`setup/`、`specs/` 结构。
- 启示：E2E 按「冒烟/无障碍/性能/mock 回归」拆配置文件，避免一个巨型 config 混装所有模式。

## 三、共识与分歧

**共识（几乎无争议）：**
1. 分层金字塔：单元（无 I/O）→ 契约/集成（真中间件或 mock server）→ E2E（真浏览器真栈）。
2. CI 门禁分层且机器强制：lint/type/单测每次提交；契约测试 + 确定性评测 PR 级；集成/E2E 至少有流水线机器跑（ nightly 或 PR，见分歧 2）。
3. pytest 侧：`--strict-markers`、`asyncio_mode=auto`、fake adapter 注入、DB 测试用真 PG 而非 SQLite 混过。
4. Playwright 侧：storageState 登录态复用、CI 重试 + trace、按 shard 拆分。
5. 时间/网络确定性：freezegun 冻结时间；fake 或 socket 禁用防止测试摸网。

**分歧（需按项目取舍）：**
1. **覆盖率阈值**：fsft 模板 90%，本仓 80%（ADR 0080 已定）。业界共识是有阈值并机器强制，数值各家不一——维持 80 即可，不跟风。
2. **E2E 跑在 PR 还是合并级**：fsft 在 PR 级（分 4 shard 控制 15 分钟超时）；更多项目放 nightly。本仓 ADR 0080 已定为合并级——**不推翻，落地即可**；若未来提级需新 ADR。
3. **契约测试形态**：手写 pytest 契约（轻、可控）vs schemathesis 自动 property-based（覆盖面广、偶发误报）。可共存：手写为主，schemathesis 可选。
4. **SQLite vs 真 PG**：langchain 单测全 fake；fsft 模板 PR 级就上真 PG。本仓当前「SQLite 测仓储 + 真 PG 集成层」，属于合理折中，不必改为单测上 PG。

## 四、对本仓的映射建议

1. pytest `addopts` 补 `--strict-markers`（langchain 同款）；marker 维持 `integration` 一个即可（分层是概念，不必四个 marker）。
2. CI 单测显式 `-m "not integration"`，替代「未设环境变量静默 skip」的隐式行为。
3. 补聊天链路测试真空：`entry.py authenticate` 单测、conversations 持久化回归（被删 `test_chat.py` 的等价物）、Aegra Agent Protocol v2 集成冒烟。
4. 合并级门禁机器化：新建 nightly/dispatch workflow（集成 + E2E + eval-answer），这是 ADR 0080「发布流水线执行」的落地而非新决策。
5. Playwright 补 storageState setup project、CI 重试 + trace、来源/反馈流 spec、`@axe-core/playwright` 无障碍冒烟（LibreChat 有 a11y 专配先例；WCAG 2.2 AA 是 AGENTS.md 硬要求）。
6. eval-answer 补数据集（含 answer/ground_truth）与 `eval_answer` 自身单测，阈值跑出基线后钉值。
7. 前端单测最小复苏：vitest 环境 jsdom + @testing-library/react，恢复被删的视图层纯函数测试；MSW 暂缓（出现第二个组件测试消费者再引入，YAGNI）。
8. 可选升级（需权衡）：oasdiff 破坏性变更门禁（比 contract-check 更强，防真·API 破坏）；pytest-socket 单元禁网；pytest-xdist 并行（当前 198 用例全量秒级，暂无必要）。
9. 明确不引入：testcontainers（与 compose 重复）、factory_boy（数据自举简单）、第三方任务编排器（ADR 0055）。
