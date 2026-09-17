# ADR 0084: TypeScript 7 原生编译器作为前端类型检查基线

日期：2026-08-30
状态：已接受

## 背景

TypeScript 7.0（Go 原生移植）于 2026-07-08 GA：经常规 `typescript` npm 包分发，
使用标准 `tsc` 命令，官方实测全量构建提速 8–12x；npm `latest` 现指 7.0.2。
项目原钉 TypeScript 6.0.2（npm alias `@typescript/typescript6`，二进制 `tsc6`），
version-baseline §4 记录的钉版理由是"typescript-eslint 8.65 仅 <6.1；TS7 勿主包直升"。

升级前破坏面核查：

1. **typescript-eslint 约束是幽灵约束**：本项目 lint 用 oxlint（Rust 自带解析器，
   不消费 TS 编译器 JS API），typescript-eslint 从未出现在任何 package.json 中；
2. oxlint / Vite 8（Rolldown + Oxc 转译）均与 tsc 版本无关，typecheck 是独立的
   `tsc -b` 步骤；`@tanstack/router-plugin` 的 peerDependencies 不含 typescript；
3. **`openapi-typescript` 7.13 在运行时 `require("typescript")` 消费编译器 JS API**
   （Printer/Factory 生成 .d.ts），而 **TS 7.0 不随包发布 API**（官方明确 7.1 才交付
   新 API）——单包直装 TS7 会让 contract-check 崩溃；
4. TS7 采纳 6.0 新默认并固化：`strict`、`noUncheckedSideEffectImports` 默认开，
   `types` 默认 `[]`，`stableTypeOrdering` 默认开且不可关；6.0 废弃项
   （`target: es5`、`moduleResolution: node10`、`baseUrl`、`module: amd/umd` 等）
   变为硬错误。本仓两个 tsconfig 均显式声明 `moduleResolution: "bundler"`、
   `module: "ESNext"`、`types`，不触碰任何废弃项；模板字面量 Unicode 语义变化
   不涉及（仓内无类型级字符串操作）。实测 `tsc -b --force` 一次通过零新错误。

## 决策

1. **采用官方"并排安装"方案（双别名）**：

   ```json
   "@typescript/native": "npm:typescript@^7.0.2",
   "typescript": "npm:@typescript/typescript6@^6.0.2"
   ```

   `tsc` 解析为 TS 7.0 原生编译器；`typescript` 包继续 re-export TS 6.0 JS API，
   供 openapi-typescript 运行时消费（`tsc6` 二进制随之保留，无命名冲突）。
2. **web 脚本 `tsc6 -b` → `tsc -b`**（build 与 typecheck 两处）。
3. **tsconfig 采纳 TS7 官方基线特性**：app 配置新增 `erasableSyntaxOnly`
   （与 `verbatimModuleSyntax` 配套的 bundler 工作流最佳实践，禁止 enum/namespace/
   参数属性等不可擦除语法，仓内零存量违例）；TS7 的新默认值
   （`noUncheckedSideEffectImports`、`stableTypeOrdering`）自动生效，不做显式
   重复声明。`--checkers`/`--builders` 并行调参维持默认（2 个项目引用的小仓无
   实测收益，不投机调参）。
4. **version-baseline §4 同步**：TypeScript 行改钉 7.0.x 双别名并注明各自用途；
   移除 typescript-eslint 钉版行（幽灵依赖从未安装，"不支持 TS7"的钉版理由随
   oxlint 方案失效）。
5. **2026-09 更新（7.1 未 GA）**：npm `latest` 仍为 7.0.2；7.1 仅 `next` 每日 dev
   （`typescript@7.1.0-dev.*`）。**不采用非正式版**。双别名保持到 7.1 正式版 +
   openapi-typescript 支持经典 JS API 后，再删 typescript6 并改钉正式 tag。

## 后果

- typecheck 实测 4.5s → 1.4s（3.2x；官方 8–12x 基准来自大仓，本项目规模小）；
  `--watch` 模式由 @parcel/watcher 的 Go 移植重建，开发反馈回路受益。
- openapi-typescript 的 peer `typescript ^5.x` 依旧名义不满足（实际消费的是
  typescript6 的 6.0 API re-export，contract-check 实测绿）——与 ADR 0083 记录的
  状态一致，不构成新增偏差。
- 钉版同步点：`apps/web/package.json`（两处别名 + 脚本）、`version-baseline` §4；
  升级任一侧须重跑 web 门禁（pnpm --filter @medicalrag/web run check、contract-check）。
- 编辑器侧可选安装 VS Code 的 TypeScript 7 扩展获得原生 LSP；不安装时编辑器
  继续按 tsconfig 工作于兼容模式，与 CI 无耦合。

## 参考

- Announcing TypeScript 7.0（devblogs.microsoft.com/typescript/announcing-typescript-7-0/，2026-07-08）
- Announcing TypeScript 7.0 RC（2026-06-18）
- typescript-eslint #12518：TypeScript 7.0.2 support（2026-07-08）
- microsoft/typescript-go（原生移植 staging 仓库，CHANGES.md 记录 6→7 行为差异）
