# ADR 0081: openai SDK 3.x 与 httpx2 生态对齐（含 Aegra/Qdrant client 升级）

日期：2026-08-24
状态：已接受

## 背景

三方库审计（2026-08-24）发现：

1. OpenAI Python SDK 3.0 起 HTTP 层切换到 **httpx2**（Pydantic 团队维护的 httpx fork，
   活跃维护、同 API、与 httpx 可共存但对象不可跨包边界）。项目停留在 openai 2.52
   （httpx 系），而自有代码的 TestClient（starlette ≥1.3）已在 httpx2 上——HTTP 客户端
   双轨且主线在迁移。
2. `packages/infra/providers/*` 自有代码 `import httpx` 并向 SDK 注入自定义 transport；
   SDK 升 3 后必须同源 httpx2，否则 transport 类型不匹配。
3. aegra-cli 钉版 0.9.24 已落后（0.10.4）；qdrant-client/server 应同步 1.19。

## 决策

1. **openai >=3.3**；`packages/infra/providers/{llm,embeddings,mineru,reranker}.py`
   及对应测试统一 `import httpx2 as httpx`（官方迁移文档认可的别名风格：最小 diff，
   对象同源）。MockTransport 注入同样走 httpx2。
2. 不引入 `httpx2.alias_httpx()` 进程级别名：那是应用层逃生舱，当前传递依赖
   （qdrant-client/langgraph-sdk/langsmith/huggingface-hub）仍拉 httpx 且工作正常，
   待上游迁移后自然移除 httpx。
3. **aegra-cli ==0.10.4**（保持 exact 钉版）；升级须过 Compose 实测门禁（ADR 版本基线门检不变）。
4. **qdrant-client >=1.19**（与 server v1.19 同步）；hybrid search/Prefetch/RRF API 无破坏性变化，
   以现有单元 + 集成测试回归兜底。
5. 前端 **@tanstack/react-table 9.x**：按官方 React 迁移指南落地——`useTable` +
   显式 `features`；全应用统一 features 集（仅 row sorting）收敛在
   `apps/web/src/lib/table.ts`（`appTableFeatures`/`AppTableFeatures`），列类型
   `ColumnDef<AppTableFeatures, TData>`；未注册 selection feature，删除死代码
   `getIsSelected` 调用。

## 后果

- HTTP 客户端主线对齐：自有代码全部 httpx2；openai 3 的 transport/http_client 注入类型匹配。
- 双包共存期持续到上游（qdrant-client 等）迁移 httpx 为止；lockfile 同时含两者属预期。
- TanStack Table v9 带来行模型性能/内存改进与 tree-shaking（未用特性不进 bundle）。
- aegra 0.10.4 的行为差异由 Compose 合并级门禁覆盖（本地无法完全验证时以 CI/发布实测为准）。

## 参考

- pydantic httpx2 迁移指南（pydantic.dev/docs/httpx2/get-started/migration）
- openai-python 3.0 发布说明 / Agents SDK release notes（http_client 迁移章节）
- TanStack Table v9 React 迁移指南（tanstack.com/table/latest/docs/framework/react/guide/migrating）
