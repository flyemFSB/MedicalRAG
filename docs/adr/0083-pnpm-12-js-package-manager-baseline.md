# ADR 0083: pnpm 12（Rust 重写）作为 JS 包管理器基线

日期：2026-08-30
状态：已接受

## 背景

pnpm 12.0.0 于 2026-08-26 发布稳定版：安装引擎（fetch/link/peer 解析）以 Rust 重写，
命令、flag、设置与 lockfile 格式沿用 v11（官方定性为"非迁移式升级"）。分发方式变化：
npm `latest` 标签仍指向 11 线，12 走 `next-12` dist-tag 与 GitHub release 自包含二进制
（官方安装文档已不再收录 corepack，CI 推荐从 `pnpm/action-setup` 迁到新 `pnpm/setup`，
后者明确"仅保留给 pnpm ≤10"）。

项目原钉 pnpm 11.13.1（version-baseline §4），Node 24.18 在 pnpm 12 兼容矩阵内。
升级前破坏面核查：

1. lockfile 无任何 git 依赖——"Git dependencies are identities" 不触发；
2. 全仓无 `pnpm install --resolution-only`（12 已移除该 flag）；
3. `pnpm-workspace.yaml` 的 `allowBuilds`/`minimumReleaseAgeExclude` 均为 pnpm 12
   认可的设置——12 起，钉版被满足时未识别的 workspace 设置会直接
   `ERR_PNPM_UNRECOGNIZED_WORKSPACE_SETTINGS` 失败（不再静默忽略），
   实测当前两个键均放行；
4. lockfileVersion 仍为 9.0，`--frozen-lockfile` 原样消费（实测零 diff、不重写）。

另一个 2026 年工具链事实：node 24.18 捆绑的 npm（12 线）默认阻止依赖的
install 脚本——实测 `npm i pnpm@12.1.0` 与 `npm i @pnpm/exe@12.1.0`（其 `preinstall:
node install.js`）被拦截后产出的 bin 均不可用，npm 安装路径在该工具链下不可行。

## 决策

1. **`packageManager` 钉 `pnpm@12.1.0`**（12 线当前最新，exact 钉版不变约定）。
2. **lockfile 不迁移**：格式 9.0 沿用；一次重解析时循环依赖会按规范化断边产生一次性
   diff（本项目依赖图无环，实测未触发）。
3. **CI 迁移 `pnpm/action-setup@v4` + `actions/setup-node` → `pnpm/setup@v2`**：
   `runtime: node@24`、`cache: true`（缓存 pnpm store）、`install: false`（保留显式
   `pnpm install --frozen-lockfile` 步骤）。web 与 security 两个 job 同步迁移；
   action 从 GitHub release 下载自包含二进制并校验 SHA-256，与 npm 12 的
   install 脚本拦截策略无关。
4. **web 镜像保留 `corepack enable && pnpm install --frozen-lockfile`**：镜像内
   corepack 0.35（node 24.18 官方捆绑版）实测可按 `packageManager` 拉起 pnpm 12.1.0
   原生二进制；pnpm 12 静态链接，对 `@pnpm/exe.linux-x64@12.1.0` 的 DT_NEEDED 扫描
   确认不需要 libatomic，`node:24.18-bookworm-slim` 无需加包。
5. 开发机安装走 `pnpm self-update next-12`（≥11.10 支持；钉版项目内同时更新 pin）。

## 后果

- 安装更快（Rust 引擎；warm store 硬链接优先）；lockfile 成为依赖图的纯函数，
  workspace 顺序变化不再产生漂移。
- 供应链政策更严：未识别的 `pnpm-workspace.yaml` 设置从静默失效升级为报错，
  拼写错误会被安装门禁拦住。
- `pnpm peers check`（读 lockfile 即可，无需重解析）当前报一个既有偏差：
  openapi-typescript@7.13.0 声明 peer `typescript ^5.x`，钉版 TS 6.0.2 不满足；
  该状态在 pnpm 11 下同样存在，运行时无碍（contract-check 绿），TS 6 钉版见
  version-baseline §4。
- 三处钉版需同步维护：根 `package.json` `packageManager`、CI action 行为、
  version-baseline §4；升级任一组件须重跑 web 门禁（pnpm --filter @medicalrag/web
  run check、contract-check、audit）与 CI docker build。
- 本机 `pnpm -r audit` 在 npmmirror 镜像源上不可用（镜像未实现 audit bulk 端点，
  与 pnpm 版本无关）；本地等价命令追加 `--registry=https://registry.npmjs.org`。

## 参考

- pnpm 12.0 发布公告（pnpm.io/blog/releases/12.0，2026-08-26）
- What's different in pnpm 12（pnpm.io/blog/whats-different-in-pnpm-12）
- pnpm 安装与 CI 文档（pnpm.io/installation、pnpm.io/continuous-integration）
- pnpm/action-setup → pnpm/setup 迁移说明（github.com/pnpm/action-setup）
