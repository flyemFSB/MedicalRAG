# Qdrant 检索 + assistant-ui 流式接线配方

> 调研日期：2026-08-04。依据：Qdrant 官方文档（qdrant.tech/documentation）、fastembed 官方仓库、assistant-ui/langchain 官方文档，并与 `packages/infra/src/medicalrag_infra/retrieval/qdrant.py`/`indexer.py` 现状对照。存储轴定案见 [ADR 0075](../adr/0075-qdrant-replaces-milvus-as-the-hybrid-retrieval-engine.md)；Aegra v2 运行时见 [aegra-runtime-implementation-recipe.md](aegra-runtime-implementation-recipe.md)。

## 1. Qdrant 混合检索（已实现，官方写法对照）

- **Hybrid Search**：dense + sparse 双路用 `prefetch` 请求，融合用 `RrfQuery(rrf=Rrf(k=60))`（官方默认 [1,100]，k=60 在建议区间）。每路 `prefetch` 携带 `using`（`dense_vec`/`sparse_vec`）、`limit`；整体 `query_filter` 做标量授权过滤（`workspace_id` + `is_eligible`）。
- **Sparse 向量**：用 fastembed `SparseTextEmbedding("Qdrant/bm25")` 静态模型，索引与检索对称、无语料库状态（官方推荐）。索引时预计算存 `sparse_vec`；检索时对查询文本实时生成。
- **Payload 元数据**：`chunk_id`/`document_id`/`source_id`/`title`/`text`/`snippet`/`workspace_id`/`is_eligible`——授权与发布过滤在 Qdrant 侧完成（ADR 0005 仅已发布版本可召回）。
- **TurboQuant 4-bit**（version-baseline §2 门禁）：dense 索引启用 4-bit 量化需在 `create_collection`/索引创建时配置量化参数；当前 `schema.py` 未启用，留待实现门禁（见 version-baseline §6.2）。
- **Collection 版本化**（ADR 0011 → ADR 0075）：每 Embedding Schema Version 一个 collection，蓝绿切换用别名。

## 2. assistant-ui 官方流式（生产浏览器经 Aegra v2）

- `useStreamRuntime({ apiUrl })`：`apiUrl` 必须为绝对 URL（`new URL('/api/agent', window.location.href).href`），相对路径会被 LangGraph SDK 的 `new URL()` 抛错。
- **结构化数据主路**：把字段放 graph state → Aegra `values` channel → 前端 `useLangChainState<T>('sources')` 读取 `stream.values[key]`。本项目 graph 已把 `analysis/evidence/safety/outcome/answer/result` 写入 state（`apps/agent/src/medicalrag_agent/graph.py`）。
- **Token 流**：graph 内 `get_stream_writer()` 写 custom channel（`{"tokens": ...}`），Aegra v2 流式带出；@langchain/react 的 `useStream` 消费内容块。
- **断点续传/取消**：`since` 续传；v2 无 `run.cancel`（Aegra 0.9.24 源码确认），取消走 legacy `runs.cancel`。
- **本地开发替代**：无 Aegra 时前端走 `POST /api/chat/stream`（FastAPI 内置 `EventSourceResponse` SSE），已在 `apps/api/src/medicalrag_api/api/chat_stream.py` 与前端 `lib/api.ts::streamChat` 实现；生产切 Aegra v2。

## 3. Nginx SSE 反代（已在 apps/web/nginx.conf）

`/api/agent` location：`proxy_http_version 1.1` + `proxy_set_header Connection ""` + `proxy_buffering off` + `proxy_cache off` + `proxy_read_timeout 3600s`（配合 Aegra `X-Accel-Buffering: no`）。

## 来源

- https://qdrant.tech/documentation/concepts/hybrid-queries/（prefetch + RRF）
- https://qdrant.tech/documentation/concepts/vectors/#sparse-vectors
- https://qdrant.github.io/fastembed/examples/Sparse_Text_Embedding/
- https://assistant-ui.com/docs/runtimes · https://langchain.com/docs（useStreamRuntime / useLangChainState）
- [aegra-runtime-implementation-recipe.md](aegra-runtime-implementation-recipe.md)（v2 stream/events、values channel、get_stream_writer）
