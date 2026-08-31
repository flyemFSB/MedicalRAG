# Spec: RAG 检索质量与摄取正确性优化（P0–P3）

> 状态：ready-for-agent · 来源：2026-08 全链路调研（对照 interview-bagu RAG 框架与 2025–2026 生产实践共识）· 术语遵循 `CONTEXT.md`

## Problem Statement

从使用者视角看，今天的系统有六类可感知的问题：

1. **换汤不换药的检索结果**。知识工作者问"阿司匹林怎么吃"和"二甲双胍有什么副作用"，得到的 Evidence 高度雷同——因为 Hybrid Retrieval 的查询文本用的是 Intent 节点的名称与描述，而不是用户重写后的真实问题。这也偏离了 ADR 0036（query embeddings use rewritten subquestions）。
2. **多轮追问失忆**。Conversation 历史传入了生成阶段的数据结构，却没有进入发给 Generation Provider 的 Message 序列，"那它的禁忌呢"这类追问无法被正确回答。
3. **多模态资料进不来**。PDF/DOCX/PPT 等 Multimodal Document 提交后 Ingestion Run 必然失败：MinerU Extraction 客户端未在 worker 组合根接线，且上传记录缺少提取阶段必需的来源地址。
4. **校验形同虚设**。validating 阶段的 checksum 与 schema 一致性由调用方硬编码为通过，损坏的索引会静默发布。
5. **内容无法下架**。Document 没有任何下架/删除路径，Chunk 一旦入库永久可检索——过期指南、撤稿文献无法清除，构成医疗合规风险。
6. **改动无护栏**。eval-retrieval 回放的是预存 fixture 而非真实管线，检索侧任何调优都无法端到端验证；Citation 质量没有独立度量。

## Solution

让用户重写后的真实问题驱动 Hybrid Retrieval（恢复 ADR 0036 合规）；加宽召回漏斗后由 Reranker 在更宽的候选集上精选，Evidence Fusion 继续负责确定性收窄；Chunk 建立大小上限与 overlap、表格原子化，并以可选的块背景补写修复指代断裂；生成端强制 Citation 标注与"资料不足"边界，并把 Conversation 历史真正纳入 Message 序列；Ingestion Run 修复 MinerU Extraction 接线与真校验；补齐 Document 下架/删除生命周期与孤儿 Chunk 扫描；评测升级为可打真实管线并新增 citation accuracy。全程遵守 Safety Boundary 与 Data Egress Policy，不改变 Evidence Answer 契约。

## User Stories

1. 作为知识工作者，我希望检索使用我重写后的真实问题（含槽位中的 Medical Entity），以便不同疾病、不同药品的问题得到各自相关的 Evidence。
2. 作为知识工作者，我希望多个候选 Intent 的检索并行执行，以便总等待时间不随意图数量线性增长。
3. 作为知识工作者，我希望系统先宽召回、再由 Reranker 精选，以便最相关的 Evidence 稳定排在答案引用的最前面。
4. 作为知识工作者，我希望超长章节的 Chunk 按句子边界切分并保留 overlap，以便跨段落的医学论述能被完整召回而不是被截断成残句。
5. 作为知识工作者，我希望表格作为原子单元被索引，以便检验参考值、剂量对照等字段关系不被切碎。
6. 作为知识工作者，我希望每个 Chunk 在索引时携带文档级背景说明，以便含指代（"该药物""上述标准"）的片段也能被正确匹配。
7. 作为知识维护者，我希望 PDF/DOCX/PPT/XLSX 及图片类 Multimodal Document 完成 MinerU Extraction 并正常发布，以便非纯文本资料进入 Knowledge Base。
8. 作为知识维护者，我希望 Ingestion Run 的 validating 阶段抽样回读已索引点比对 checksum 并核对 Embedding Schema Version，以便损坏或不兼容的索引不会静默发布。
9. 作为知识维护者，我希望 Document 可以下架（立即退出检索）与删除（级联清除全部 Chunk），以便过期指南、撤稿文献不再出现在任何答案中。
10. 作为运营管理员，我希望有定期孤儿 Chunk 扫描，以便索引与 Document 状态保持一致并可审计。
11. 作为知识工作者，我希望答案中每条断言都标注 Citation 编号且编号对应真实存在的 Evidence，以便逐条溯源。
12. 作为知识工作者，我希望 Evidence 不足时得到明确的"资料不足"回答而非推测，以便信任系统的 Safety Boundary。
13. 作为知识工作者，我希望多轮追问保留 Conversation 历史，以便省略主语的后续问题仍能命中正确主题。
14. 作为知识工作者，我希望 Analysis Depth 只提高检索预算与 Evidence 封顶而不改变安全行为，以便深浅两种模式的行为都可预期（ADR 0069）。
15. 作为平台开发者，我希望嵌入调用按固定批大小分批，以便大 Document 不触发 External Model Provider 限流。
16. 作为平台开发者，我希望 token 计数使用真实 tokenizer 而非空格切分，以便块预算与成本核算建立在可信数字上。
17. 作为平台开发者，我希望 eval-retrieval 支持打真实管线（Retriever + Evidence Fusion）的模式，以便检索侧改动有端到端回归护栏。
18. 作为平台开发者，我希望新增 citation accuracy 指标，以便答案引用的质量可以被量化追踪。
19. 作为平台开发者，我希望 RAGAS 评估补充 context precision 与 context recall，以便失效能被定位到检索层还是生成层。
20. 作为运营管理员，我希望查询侧 Embedding 结果被缓存（归一化文本为键），以便高频问题降低延迟与调用成本。
21. 作为合规评审者，我希望所有发往 External Model Provider 的文本继续仅含 Data Egress Policy 批准的 De-identified Medical Data，以便 Identifiable Patient Data 永不出境。
22. 作为平台开发者，我希望每次质量改动一次只改一个变量并用评测集对照，以便指标回退可归因、可回滚。

## Implementation Decisions

### Phase 0 — 正确性修复（先于一切调优）

1. **恢复 ADR 0036 合规（非新决策）**：`IntentQuery` 扩展携带 rewritten question 与槽位值；Hybrid Retrieval 的 dense 与 sparse 查询文本以 rewritten question 为主体、槽位 Medical Entity 按版本化 query-input 格式附加；Intent 节点名称/描述降为辅助信号。低置信实体与未验证的患者细节不得进入查询（ADR 0036 后果条款）。
2. **MinerU Extraction 接线**：worker 组合根注入提取客户端；Document 提交时持久化来源地址供提取阶段读取；提取失败落入既有的 FAILED 终止态，不新增状态。
3. **validating 真校验**：抽样回读已索引点比对 chunk checksum；Embedding Schema Version 从 collection 元数据读取并与预期比对；任一不一致 → Run 落 FAILED。
4. **嵌入分批**：固定批大小常量循环调用 Embedding Provider；dense 向量不再整体写入 run 元数据 JSON 列，仅保存统计信息。
5. **token 计数**：改用项目钉版的 tokenizer 计算块 token 数。

### Phase 1 — 检索质量主战场

6. **分块策略演进（需新 ADR，修订 ADR 0034）**：结构优先原则保留；单 Chunk 文本超过上限（默认约 500 token，按 tokenizer 计）时按句子边界递归切分；相邻子块保留 10–15% overlap；表格节整表原子化不切分。Chunk 标识与溯源规则不变。
7. **Chunk 背景补写（需新 ADR）**：激活既有 enrichment 端口，用低成本模型按文档顺序为每个 Chunk 生成 50–100 token 的背景说明；同一份补写文本同时进入 dense 嵌入文本与 sparse 索引文本（业界称 Contextual Retrieval 配方，实测检索失败率显著下降）；功能开关控制；输入文本策略变化使 Embedding Schema Version 递增 → 必须全量重建索引（ADR 0011/0036 硬约束）；利用同文档顺序处理摊薄调用成本。
8. **召回漏斗加宽**：每路召回 limit 提升至可配置的宽召回值（默认 50）；Reranker 在宽候选集上打分；最终收窄仍由 Evidence Fusion 的 context_cap 负责（ADR 0039 职责不变）；Analysis Depth 的预算加倍语义不变。
9. **多意图查询并行化**：各 Intent 查询并发执行；单路失败不阻塞其余路，失败路按既有降级语义处理。

### Phase 2 — 生成质量

10. **Prompt 加固**：Evidence 行格式为 Citation 标签 + 标题 + 片段；system 指令增加三条硬约束——仅依据给定 Evidence 回答、逐条断言标注 Citation 编号、Evidence 不足时明确说明资料不足；user Message 组装顺序为脱敏截断后的 Conversation 历史 + 问题置末。
11. **Conversation 历史进入生成**：Generation Context 中已加载的记忆真正写入发送给 Generation Provider 的 Message 序列；出境内容遵守 Data Egress Policy（仅 De-identified Medical Data）。

### Phase 3 — 工程完备性

12. **Document 生命周期（需新 ADR）**：下架 = 发布资格标记置否（Published Version 失效，软删，立即可逆）；删除 = 按 document_id 物理级联删除全部 Qdrant 点；两者均经 outbox 由 worker 异步执行（与 ADR 0013 异步摄取同款模式）；新增定期孤儿 Chunk 扫描任务。
13. **查询 Embedding 缓存**：infra 层以装饰器包裹 Embedding Provider，归一化文本为键、Redis 存储、TTL 兜底；明确不做答案级语义缓存（医疗场景误命中风险）。
14. **评测升级**：eval-retrieval 新增 live 模式（对真实 Retriever + Evidence Fusion 打分，与 fixture 回放模式并存）；新增 citation accuracy 指标；RAGAS 补 context_precision / context_recall；golden set 扩充至不少于 50 条，覆盖正常、边界、对抗三类。

### 决策前置条件

- 三个新 ADR 先行：分块策略演进（修订 0034）、Chunk 背景补写、Document 生命周期；随后更新 wayfinder map 与 spec/architecture 引用链。
- API 面（Document 下架/删除路由）变更的 commit 必须同步 openapi-typescript 生成产物，保持 contract-check 绿（ADR 0071）。

## Testing Decisions

- **只测外部行为**：通过 fake 端口断言"收到了什么查询文本/什么 Message 序列/什么删除指令"，不断言内部调用次数、私有方法等实现细节。
- **五个既有 seam，零新增**：
  1. 聊天编排核心的流式入口（medical-core）——rewritten question 进入检索查询、漏斗加宽、Analysis Depth 预算、Conversation 历史进入生成、空证据/降级路径；
  2. Qdrant 混合检索适配器（Retriever 端口实现）——查询文本构造规则与多意图并行；
  3. Ingestion Service + 分块纯函数——大小上限/overlap/表格原子化、嵌入分批、真校验、MinerU 接线、背景补写、tokenizer 计数；
  4. Generation/Classifier Provider（httpx transport 注入录制请求体的既有模式）——Prompt 加固与 Citation 约束；
  5. 评测 runner CLI——live 模式与 citation accuracy。
- **生命周期测试**走两个既有 seam：API 契约测试（下架/删除路由）+ worker 服务测试（级联删除与孤儿扫描）。
- **Prior art**：medical-core 内存适配器单元测试、worker 的 IngestionService 测试、provider 层 transport 注入测试、api 契约测试、evaluation 的 fixture 回放测试——全部沿用其既有形态。
- **门禁联动**：PR 级跑 eval-retrieval（live 模式就绪后切换为主力）；Embedding Schema Version 递增的重建过程需迁移测试覆盖。

## Out of Scope

- GraphRAG 与 Structured Medical Metadata 图谱化（语料规模不支持索引成本）。
- HyDE（已有 Intent 路由 + 查询重写，延迟敏感）。
- 开环 Agentic 检索循环（受控有界流水线是医疗安全设计，不推翻）。
- 答案级语义缓存（误命中返回错误医疗答案的风险不可接受）。
- 更换向量库或嵌入模型；多 Workspace 分片。
- MCP 兼容（ADR 0051 已排除）。
- 前端 UI 变更（本 spec 全部为后端与管线行为）。

## Further Notes

- **实施纪律**：Phase 内一次只改一个变量，每步跑评测对照，指标无提升即回滚——这是 bagu 框架与 2026 生产共识一致的调优纪律。
- **parity 门禁**：涉及 ragent 行为对齐的能力，须在其迁移矩阵行补通过 fixture 方算完成（ADR 0049）。
- **成本提示**：Chunk 背景补写是一次性索引成本（prompt caching 摊薄后约为每百万文档 token 一美元量级）；Embedding Schema Version 递增触发的全量重建应安排在低峰期并分批推进。
- **优先级依据**：Phase 0 是 bug 修复；Phase 1 中"查询文本构造"预计单项收益最大（当前同类问题检索输入完全相同）；其余按 ROI 递减排列。
