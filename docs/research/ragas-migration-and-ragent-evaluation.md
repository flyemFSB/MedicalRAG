# RAGAS 迁移与 Ragent 评测边界研究

## 研究边界

- **研究日期**：2026-07-26。
- **研究目标**：核对同级目录 `D:\yzb\ragent` 中 Ragent 的 `rag/eval` 实现、评测数据/脚本/CI 状态，并对照 RAGAS 官方文档与 `v0.4.3` 源码，确定 MedicalRAG 的迁移边界、指标选择、脱敏和 CI 使用方式。
- **本文件性质**：只读源码/官方资料研究结论与设计建议；本次只写入本文件，不修改实现代码、spec、architecture、ADR 或 Wayfinder 票据。
- **来源限制**：事实只引用 Ragent 本地源码、Ragent 本地文件清单，以及 RAGAS 官方文档/官方 GitHub 源码。建议和风险判断明确标为本项目建议，不冒充上游承诺。

## 结论摘要

1. **Ragent 没有真正依赖 Python `ragas`**。Ragent 是 Java/Spring Boot 工程；源码中没有 Python 包管理文件或 `ragas` 依赖，`rag/eval` 是 Java Controller/DTO/配置。它提供的是一个外部评测契约，契约字段有意对齐 RAGAS 常用的 `retrieved_contexts`、参考文档/Chunk ID 和检索指标，而不是在 JVM 内嵌 RAGAS。
2. **当前 `/rag/eval` 是检索/意图评测接口，不是答案质量评测接口**。它执行问题改写、子问题意图解析和检索，返回上下文、ID、分支标记、意图叶子和延迟；不返回 `response`。因此当前接口可以直接支持外部的检索、意图和延迟评测，但不能直接支持 RAGAS 的 Faithfulness、Response Relevancy、Factual Correctness、Semantic Similarity 等答案指标。
3. **最适合第一阶段的是 ID-based 检索指标及项目自有确定性指标**：RAGAS `IDBasedContextPrecision`/`IDBasedContextRecall`、Ragent 意图 Top-1、空召回率、分支正确性、延迟和自定义 MRR/nDCG。ID-based 指标应在同一粒度上使用 gold Chunk ID 或 gold 文档 ID；RAGAS 的实现把 ID 转成集合，因此不能替代保序的排名指标。
4. **医疗场景不能把任何 RAGAS LLM-as-a-judge 分数当作临床安全门禁**。Faithfulness 可作为“回答是否受检索上下文支持”的二级信号；Factual Correctness、Context Recall、Context Precision、Noise Sensitivity、Aspect/Rubric 评分可用于离线诊断或回归，但都需要专家参考、模型/提示词校准、中文验证和人工抽检。它们不能证明诊断、用药、剂量、禁忌证、时效性或安全升级建议正确。
5. **推荐两个隔离 profile**：`ragent-eval-retrieval` 只暴露检索契约并使用脱敏/合成数据、无外部 LLM；`ragent-eval-answer` 仅在隔离评测环境捕获答案后运行 RAGAS 答案指标。生产环境必须关闭评测端点；当前被检查的 `application.yaml` 却把 `app.eval.enabled` 配为 `true`，这是迁移前必须处理的配置风险。

## 1. Ragent 实际实现：依赖还是外部契约

### 1.1 代码和依赖证据

Ragent 的评测实现只有以下三个类：

- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalController.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalProperties.java`
- `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalResponse.java`

`EvalController` 是 Spring `@RestController`，在 `app.eval.enabled=true` 时注册 `GET /rag/eval`。请求只接收一个 `question`，随后调用 `QueryRewriteService`、`IntentResolver` 和 `RetrievalEngine`，没有生成答案的 LLM 调用。[R1]

`EvalResponse` 是 Java DTO，输出 `retrievedDocIds`、`retrievedChunkIds`、`retrievedContexts`、与上下文逐项对应的 `retrievedContextDocIds`、`mcpContext`、`hasMcp`、`hasKb`、`subIntents`、`intentLeafIds` 和 `latencyMs`。[R2] 这些字段是评测交换格式，不是对 Python 包的 import 或运行时调用。

对 `D:\yzb\ragent\pom.xml`、各模块 `pom.xml`、全仓文件名和文本进行检查：未发现 `ragas` Maven 坐标、Python `pyproject.toml`、`requirements*.txt`、`uv.lock`、`poetry.lock`、Python 源码或 Notebook。Ragent 是 Java/前端工程，现有脚本只有 `D:\yzb\ragent\scripts\sse_queue_test.sh`，它不是 RAGAS 评测 runner；未发现 `.github` CI 配置、JSONL/CSV/TSV 评测集或可执行的 RAGAS 评测脚本。

源码中确实有注释提到 `reference_doc_ids`、`context_precision`、`context_recall` 和 `intent_l2`，但这些只出现在 DTO 的字段契约说明；备份 prompt 中的“RAGAS 友好回答原则”也只是提示词文本，不构成 Python 依赖。[R2][R3]

### 1.2 开关和暴露风险

`EvalProperties` 的文档把评测模式描述为默认关闭、由独立 profile 打开；`EvalController` 也使用 `@ConditionalOnProperty`。[R1][R4] 但当前 `D:\yzb\ragent\bootstrap\src\main\resources\application.yaml:312-315` 明确设置了：

```yaml
app:
  eval:
    enabled: true
```

另外，`IdempotentSubmitAspect` 在 `app.eval.enabled=true` 时会绕过幂等锁。[R5] 这说明评测开关不仅控制评测路由，也会改变通用请求行为。`EvalController` 源文件没有展示专用鉴权、网络限制或脱敏逻辑；不能据此断言整个应用没有全局安全层，但不能把“有全局安全层”当成已证明的评测隔离。评测 profile 必须显式配置内部网络、认证、访问日志脱敏和数据范围。

还有一个需要迁移时清理的文档/实现不一致：`EvalProperties` 的注释提到 `/rag/eval/sync` 和 `EvalRetrievalCaptureAspect`，但对 Ragent 全仓源码搜索未发现该路由或该切面；实际可见的 Controller 只有 `/rag/eval`。因此不能把这些注释当作已存在的同步评测能力。

### 1.3 对外契约的正确理解

推荐把当前接口理解为：

```text
Ragent Java service (system under test)
        │ GET /rag/eval?question=...
        ▼
external Python runner / adapter
        │ normalize to RAGAS SingleTurnSample or deterministic records
        ▼
RAGAS metrics + project-specific retrieval/intent/safety checks
```

Python runner 可以依赖 `ragas`；Ragent 不需要依赖它。这样可以独立升级 RAGAS、替换评测模型、运行确定性指标，也不会把评测包、评测模型凭据和评测数据带入生产 JVM。

## 2. Ragent 契约到 RAGAS 样本字段的映射

RAGAS `v0.4.3` 的 `SingleTurnSample` 支持 `user_input`、`retrieved_contexts`、`reference_contexts`、`retrieved_context_ids`、`reference_context_ids`、`response`、`reference` 和 rubric 等字段。[G1] Ragent 字段应按下表映射，额外字段保留在 runner 的旁路记录中，不要伪装成 RAGAS 的标准字段。

| RAGAS/评测字段 | Ragent 当前来源 | 适用范围与注意事项 |
|---|---|---|
| `user_input` | 请求中的 `question` | 记录原问题；若要评估改写质量，另存 `subIntents`，不要覆盖原问题。 |
| `retrieved_contexts` | `retrievedContexts` | Chunk 文本，保留 Ragent 顺序；会包含敏感内容，必须先经过评测数据边界检查。 |
| `retrieved_context_ids` | 首选 `retrievedChunkIds` | 只能与 Chunk 粒度的 gold ID 比较；Ragent 已按 Chunk ID 去重。 |
| `reference_context_ids` | 外部评测集的专家标注 | 推荐使用稳定、不可逆、非患者身份的 Chunk ID；若 gold 只有文档级 ID，则改用 `retrievedDocIds`。 |
| `reference_contexts` | 外部 gold 证据文本 | 只有有专家审阅的 gold 证据文本时才填；不能把“相似文档”自动当作临床 gold。 |
| `reference` | 外部参考答案 | Ragent 当前接口不提供；必须来自脱敏、版本化、专家审阅的数据集。 |
| `response` | 当前接口没有 | 因此当前接口不能直接跑答案质量指标；需要另一个答案捕获 seam 或完整聊天回放。 |
| `retrievedDocIds` | Ragent 返回的文档级 ID | 文档级覆盖率/审计；不要和 Chunk gold 混用。 |
| `retrievedContextDocIds` | 与 `retrievedContexts` 同序、保留 null 的文档 ID | 用于分析 Chunk→Document 对齐和数据质量；不应替代 Chunk ID。 |
| `subIntents` / `intentLeafIds` | Ragent 返回的改写子问题和 top-1 叶子 ID | 使用项目确定性脚本计算拆分一致性、意图 Top-1/Top-k；不是 RAGAS 内置 RAG 指标。 |
| `hasMcp` / `mcpContext` / `hasKb` / `latencyMs` | Ragent 返回 | `hasMcp`/`mcpContext` 只保留在源审计记录中并在目标中标记 rejected；MedicalRAG 只保留适用的知识库分支、延迟和数据泄露审计字段。 |

Ragent 的 `flattenChunks` 按 Chunk ID 去重并保持首次顺序；文档 ID 列表也按首次出现去重。[R1] RAGAS `IDBasedContextPrecision` 和 `IDBasedContextRecall` 在源码中会把 retrieved/reference ID 都转换为集合后计算命中，因此会丢掉排名和重复次数。[G3][G4] 结论是：它们适合作为集合级 precision/recall 基线，不适合作为唯一的 top-k 排名质量指标。排名必须由 runner 另算 MRR、nDCG、Recall@k 或项目定义的医疗证据优先级指标。

## 3. 指标适用性

### 3.1 推荐的第一阶段指标

#### A. ID-based Context Precision / Recall：推荐作为检索基线

RAGAS 官方源码提供 `IDBasedContextPrecision`，要求 `retrieved_context_ids` 与 `reference_context_ids`；`IDBasedContextRecall` 使用同样的两列，并按 gold ID 被召回的比例计算。[G3][G4] 这与 Ragent 已返回的 Chunk/文档 ID 契约最匹配，而且不需要把医疗文本发送给评测 LLM。

使用规则：

- gold 和 retrieved 必须同粒度、同版本、同权限范围；Chunk 规则或索引版本变化时重新生成 gold manifest。
- ID 必须是稳定的业务评测 ID，不能使用患者姓名、住院号、身份证号、手机号或含身份信息的文件名。
- doc-level 结果只回答“文档有没有覆盖”，不能证明具体 Chunk 足以支撑答案；医疗评测优先保留 Chunk-level gold。
- 另算保序排名指标，因为 RAGAS ID-based 实现按集合计算。

#### B. 项目确定性指标：必须和 RAGAS 分开

当前 Ragent 契约天然支持以下确定性检查：

- 意图叶子 Top-1/Top-k 与外部 `intent_l2` gold 的准确率；
- 子问题数量、顺序和拆分稳定性；
- 适用的知识库分支是否符合测试样本预期；MCP 分支不进入目标评测契约。
- 空召回率、重复 Chunk 率、Chunk→Document 映射缺失率；
- Recall@k、MRR/nDCG、每意图/每知识库分层召回率；
- P50/P95 `latencyMs`、超时率和错误率。

这些指标比把所有信息压成一个 RAGAS 分数更可解释，也能覆盖医疗系统的授权过滤、证据版本和分支行为。

### 3.2 可用但必须放在离线/诊断层的指标

| 指标 | RAGAS 官方契约/实现 | MedicalRAG 建议 |
|---|---|---|
| LLM Context Precision | 有 reference 版本要求 `user_input`、`retrieved_contexts`、`reference`；无 reference 版本使用 `response` 估计 context utilization。[G5] | 有专家参考答案时作为上下文排序/有用性诊断；当前 `/rag/eval` 没有 `reference` 或 `response`，不能直接使用。医疗场景不作为安全门。 |
| LLM Context Recall | 要求 `user_input`、`retrieved_contexts`、`reference`，源码让 LLM 判断参考答案句子是否可归因于上下文。[G6] | 用于分析证据覆盖缺口；参考答案必须是专家审阅的“应覆盖事实”，不能只是一段自由生成答案。 |
| Non-LLM Context Precision/Recall | 可用 `retrieved_contexts` 与 `reference_contexts` 做相似度比较；也有 ID-based 版本。[G5][G6] | 可作为文本/证据 baseline；字符串相似或通用相似度对医学同义词、单位、否定和关系不够可靠。ID-based 优先。 |
| Faithfulness | 需要 `user_input`、`response`、`retrieved_contexts`；源码先把回答拆成 statements，再让 LLM 对上下文做 NLI 判断。[G7] | 适合作为“回答是否越过已检索证据”的二级信号，特别是引用绑定回归；不等于临床事实正确，也不检查禁忌证、剂量或时效。 |
| Response Relevancy | 需要 `user_input`、`response`；源码用 LLM 从回答生成问题，再用 embeddings 计算相似度。[G8] | 只评估答非所问/冗余程度；不是医学正确性指标，且当前 endpoint 没有 response。 |
| Factual Correctness | 需要 `response`、`reference`，使用 claim decomposition/NLI；`v0.4.3` 源码默认 `language="english"`。[G9] | 只有在中文 prompt、中文医学参考答案和专家标注完成独立验证后才可做离线信号；不应直接作为中文医疗 CI gate。 |
| Noise Sensitivity | 需要 `user_input`、`response`、`reference`、`retrieved_contexts`，用 LLM 判断相关/无关上下文造成的错误声明。[G10] | 适合研究“加入干扰 Chunk 后是否污染回答”；成本高、解释依赖评测 LLM，放 nightly 或专项实验。 |
| Context Entity Recall | 需要 `reference` 与 `retrieved_contexts`，先用 LLM 抽实体再计算交集召回。[G11] | 仅作为疾病名、药品名、检查名等实体覆盖的诊断指标；不能覆盖否定、剂量、时间、因果、适应证/禁忌证关系。 |

### 3.3 不应作为当前主线指标

- **Semantic Similarity / Answer Similarity**：官方实现只要求 `reference` 与 `response`，依赖 embeddings 计算余弦相似度。[G12] 语义相似可能奖励“措辞相近但临床错误”的回答，也可能惩罚安全的保守回答、拒答和带限制条件的回答，不能作为医疗真值代理。
- **Aspect Critic、Simple Criteria、Rubrics**：RAGAS 支持自定义标准和 rubric，适合构造“是否给出诊断/处方”“是否正确升级急症”“是否有证据引用”“是否表达不确定性”等审阅任务；但它们本质仍是 LLM 评分。应与人工金标准做一致性验证，只作为 advisory 或人工复核排序，不直接自动放行临床输出。[G13]
- **Agent/tool-call 和多模态指标**：RAGAS 官方指标列表包含 Tool Call、Agent Goal、Multimodal 等类别。[G14] 当前 Ragent eval 返回的是 `mcpContext` 字符串和布尔分支标志，不是可验证的 tool-call 序列、工具参数和多模态样本，所以不能直接套用。

## 4. 医疗场景的迁移边界

### 4.1 建议保留的边界

1. **Ragent 作为 SUT，Python runner 作为评测适配层**。runner 负责调用 Ragent、重试/超时、字段校验、转换为 `SingleTurnSample`、执行 RAGAS 和保存脱敏结果；不把 runner 逻辑塞入 Java 服务。
2. **第一阶段只迁移 retrieval contract**。输入是脱敏问题，输出是 retrieved Chunk/doc IDs、文本、意图、分支和延迟；用确定性指标和 ID-based 指标建立基线。
3. **答案指标另设 answer capture seam**。只有取得最终 `response`、对应的 `reference`/expert rubric、模型和 prompt 版本后，才运行 Faithfulness、Factual Correctness、Response Relevancy 等；不要用检索接口伪造空答案。
4. **保留适用的 Ragent 额外字段但不强行映射**。意图、知识库分支和延迟是目标行为契约；MCP 字段只作为 rejected source capability 记录，不进入 MedicalRAG 评测契约。
5. **把 RAGAS 版本、评测 LLM、embedding、prompt、temperature、重试、数据集版本和阈值写入评测 manifest**。RAGAS 官方源码会自动给 LLM/embeddings 指标注入 provider，也支持 callbacks/cost tracking；如果不锁定这些输入，跨运行比较不可靠。[G15]

### 4.2 不应跨越的边界

- 不在 Ragent 的 Maven 运行时引入 Python、RAGAS 或 Python 子进程。
- 不让评测 LLM 参与授权、检索过滤、证据选择、医疗安全短路或生产回答提交。
- 不用通用 RAGAS 分数替代医疗专家对诊断、药品、剂量、禁忌证、急症升级、拒答和引用完整性的审核。
- 不把真实生产会话、原始 Chunk 或带身份的文档直接上传到外部评测 LLM/Embedding 服务。
- 不把 Ragent 的 `mcpContext` 带入 MedicalRAG 评测 payload；该字段属于被拒绝的源能力，不能被误当作 retrieved context。

## 5. 推荐 profile

以下是建议名称，不代表当前 Ragent 已经实现这些 profile：

### `ragent-eval-retrieval`

- 只在隔离的 ephemeral/staging Ragent 实例开启 `app.eval.enabled`。
- 只接收合成或批准的去标识化数据；数据集和索引 manifest 固定版本。
- Python runner 只运行 schema 校验、ID-based precision/recall、MRR/nDCG、意图、分支、空召回和延迟；不调用外部 judge LLM。
- 端点只允许 CI 私网访问，使用专用 service credential；访问日志不得记录完整 query string。
- 评测结束销毁临时数据和索引，保留 manifest、聚合分数和最小失败样本摘要。

### `ragent-eval-answer`

- 在与生产隔离的环境运行完整回答回放，显式记录 `response`、证据包、引用绑定、模型/提示词版本和参考答案版本。
- 先跑确定性安全/结构检查，再跑 RAGAS Faithfulness、Context Precision/Recall、Factual Correctness、Response Relevancy 等离线诊断。
- LLM/Embedding provider 使用固定 allowlist、固定模型版本或可追溯快照；所有请求经过数据出站策略。
- 结果只能进入评测报告和人工复核，不自动改变生产配置或发布答案。

### `clinical-safety-review`

- 不是“更多 RAGAS 指标”，而是专家审核 profile。
- 数据集必须覆盖证据不足、拒答、急症升级、药物剂量、禁忌证、否定句、时间版本冲突、多问题和错误/恶意文档等医疗失败模式。
- RAGAS rubric/Aspect Critic 可用于排序和辅助摘要；最终门禁使用专家标签、规则检查和抽样复核。

## 6. 数据脱敏与数据集分层

这是本项目建议，不是 RAGAS 的隐私保证：

1. **默认不用真实患者数据**。优先使用合成病例、公开且获准的医学资料、或经过正式审批的去标识化样本；去标识化不是“只删姓名”。
2. **对问题、reference、retrievedContexts、文档名和日志统一扫描**，处理直接身份标识、日期/地点组合、账号/病案号、自由文本中的罕见身份线索；自动规则之后必须人工抽样。
3. **保持临床语义不变量**。脱敏不能破坏否定、剂量和单位、时间顺序、年龄组、药品/疾病关系、禁忌证和升级条件；否则评测分数没有临床解释。
4. **ID 与文本分离**。CI 只使用不可逆稳定评测 ID；gold ID 到内部文档/Chunk 的映射放在受控存储，不进入 RAGAS 上传 payload、报告 HTML 或普通日志。
5. **分层并锁版本**。至少按 intent、是否需要拒答、证据是否充分、语言、文档类型、版本冲突和问题复杂度分层；拆分 train/dev/holdout，holdout 不参与阈值调参。
6. **禁止原始内容泄露到 URL 和日志**。Ragent 当前接口是 GET query parameter；医疗问题可能进入代理、网关或访问日志。迁移实现至少要在私网调用、关闭/脱敏 query logging，并评估是否需要在新适配层使用 POST 或内部 RPC。
7. **外部评测最小化**。RAGAS 的 LLM 指标会把问题、回答、参考和上下文交给评测 LLM；Response Relevancy 还会使用 embeddings。[G7][G8] 因此只有在数据出站策略批准后，才可运行答案 profile；retrieval profile 默认选 ID-based 指标，避免发送原文。

## 7. CI 使用方式

### Pull Request gate：确定性、无外部 judge

- 启动隔离 Ragent eval 实例，使用小型合成数据集和固定索引 fixture。
- 检查 `/rag/eval` 响应 schema、Chunk/doc 粒度、上下文与 `retrievedContextDocIds` 对齐、未知 Chunk 映射、意图叶子和分支标志。
- 运行 ID-based Context Precision/Recall、Recall@k/MRR/nDCG、intent Top-1、空召回率、重复率和 P95 延迟。
- 检查默认/生产配置不能把 `app.eval.enabled` 打开；这是对当前配置风险的回归保护，而不是本次直接修改配置。
- 不上传原文、不调用外部 LLM/Embedding、不把评测问题放入公共 CI 日志。

### Nightly / release candidate：受控 LLM 评测

- 使用冻结的去标识化 holdout，固定 RAGAS 版本（本研究核对的是 `v0.4.3`）、评测 LLM、embedding、prompt 和阈值 manifest。
- 运行答案 profile 的 Faithfulness、Context Precision/Recall、Factual Correctness、Response Relevancy、Noise Sensitivity 等，并按 intent/语言/安全类别分层报告；总体平均值不能掩盖高风险子集退化。
- 记录 token/cost、失败/重试、NaN、超时和模型版本；将外部 judge 失败与业务质量失败分开。
- 阈值采用“与已批准基线相比不得回退 + 高风险类别不得退化”的组合，而不是只设一个全局平均分。
- 生成的 artifact 只保留聚合结果、ID、脱敏失败摘要和 manifest；原始文本留在受控环境并设定保留期限。

### Release / clinical review gate：专家与规则优先

- 对涉及拒答、诊断/处方边界、剂量、禁忌证、急症升级、引用和时效性的样本，使用专家盲审或双人复核。
- 规则检查和专家标签是发布门禁；RAGAS 只提供可重复的辅助信号和回归定位。
- 任何评测 LLM 分数异常时，抽取 statement、上下文、reference 和模型版本进行人工复核，不能直接把分数写成临床结论。

## 8. 建议的最小外部 runner 记录格式

实现时可以把 Ragent 原始响应与 RAGAS 行分开保存：

```json
{
  "case_id": "eval-opaque-0001",
  "user_input": "脱敏后的问题",
  "retrieved_contexts": ["脱敏后的 chunk 文本"],
  "retrieved_context_ids": ["chunk-opaque-01"],
  "reference_context_ids": ["chunk-opaque-01"],
  "reference": "仅在 answer profile 提供的专家参考答案",
  "response": "仅在 answer profile 提供的脱敏系统回答",
  "ragent": {
    "retrieved_doc_ids": ["doc-opaque-01"],
    "retrieved_context_doc_ids": ["doc-opaque-01"],
    "sub_intents": ["脱敏子问题"],
    "intent_leaf_ids": ["intent-opaque-01"],
    "has_kb": true,
    "latency_ms": 42
  },
  "manifest": {
    "ragent_build": "记录具体构建标识",
    "index_version": "记录索引版本",
    "dataset_version": "记录数据集版本",
    "ragas_version": "0.4.3",
    "judge_model": "仅在 answer profile 记录"
  }
}
```

`reference`、`response` 不应在 retrieval-only profile 中填空字符串来“凑字段”；指标需要的字段缺失时应跳过该指标并报告 `not_applicable`，避免把无答案样本误算为低分或高分。

## 9. 官方与本地一手来源

### Ragent 本地源码

- [R1] `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalController.java`：评测开关、`GET /rag/eval`、改写/意图/检索调用和响应构造。
- [R2] `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalResponse.java`：返回字段及其评测粒度说明。
- [R3] `D:\yzb\ragent\bootstrap\src\main\resources\prompt\buckup\answer-chat-kb-bitmall-v2.st`：唯一命中的 “RAGAS 友好” 文本，属于备份 prompt，不是依赖声明。
- [R4] `D:\yzb\ragent\bootstrap\src\main\java\com\nageoffer\ai\ragent\rag\eval\EvalProperties.java`：评测 profile 文档和 `app.eval` 配置属性。
- [R5] `D:\yzb\ragent\framework\src\main\java\com\nageoffer\ai\ragent\framework\idempotent\IdempotentSubmitAspect.java`：评测开关打开时绕过幂等锁的行为。
- `D:\yzb\ragent\bootstrap\src\main\resources\application.yaml`：当前 `app.eval.enabled: true` 配置。
- `D:\yzb\ragent\pom.xml`、各模块 `pom.xml`、`D:\yzb\ragent\scripts\sse_queue_test.sh`：依赖与脚本盘点依据。

### RAGAS 官方文档与源码（v0.4.3）

- [G1] [SingleTurnSample / dataset schema](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/dataset_schema.py)
- [G2] [RAGAS available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)；[metrics overview](https://docs.ragas.io/en/stable/concepts/metrics/overview/)
- [G3] [Context Precision source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_context_precision.py)：LLM、non-LLM 和 ID-based Context Precision。
- [G4] [Context Recall source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_context_recall.py)：LLM、non-LLM 和 ID-based Context Recall。
- [G5] [Context Precision official guide](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/docs/concepts/metrics/available_metrics/context_precision.md)
- [G6] [Context Recall official guide](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/docs/concepts/metrics/available_metrics/context_recall.md)
- [G7] [Faithfulness source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_faithfulness.py)
- [G8] [Response Relevancy source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_answer_relevance.py)
- [G9] [Factual Correctness source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_factual_correctness.py)
- [G10] [Noise Sensitivity source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_noise_sensitivity.py)
- [G11] [Context Entity Recall source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_context_entities_recall.py)
- [G12] [Semantic Similarity source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_answer_similarity.py)
- [G13] [Aspect Critic / general-purpose metrics source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/_aspect_critic.py)
- [G14] [RAGAS metric registry](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/__init__.py)：RAG、agent/tool、multimodal、natural-language 和 rubric 指标清单。
- [G15] [RAGAS evaluation source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/evaluation.py)：指标初始化、LLM/embedding 注入、callbacks/cost tracking，以及 `evaluate()` 已 deprecated 的源码提示。
- [G16] [RAGAS experiment source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/experiment.py)：`@experiment`、数据集迭代、并发执行和结果保存接口。
- [G17] [RAGAS v0.4.3 release](https://github.com/vibrantlabsai/ragas/releases/tag/v0.4.3)
- [G18] [RAGAS package metadata and dependencies](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/pyproject.toml)：Python 包、核心依赖、optional features 和 CLI 声明。
