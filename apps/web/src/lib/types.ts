// 前端领域类型（对齐 CONTEXT.md 正名；仅作类型，不含业务逻辑）。
// 运营端点已全部落地：本层由 lib/api.ts 从 openapi-typescript 生成类型（ADR 0071）映射而来。

/** 摄取运行阶段状态（对应 medical-core 摄取状态机）。 */
export type StageStatus = "pending" | "running" | "succeeded" | "failed";

/** 摄取运行状态（九阶段：accepted → … → indexing → validating → published）。 */
export type IngestionStatus =
  | "accepted"
  | "extracting"
  | "chunking"
  | "embedding"
  | "indexing"
  | "validating"
  | "published"
  | "failed";

/** 运行结果（对应聊天状态机的终态）。 */
export type RunOutcome =
  | "completed"
  | "guidance"
  | "empty"
  | "fallback"
  | "cancelled"
  | "failed";

/** 语义状态（与 DESIGN.md §2.3 一致，供状态徽章使用）。 */
export type SemStatus = "success" | "warning" | "error" | "info" | "neutral";

/** 知识库（用户作用域的医疗来源集合）。 */
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
}

/** 文档（提交给知识库的原始来源，含摄取状态）。 */
export interface Document {
  id: string;
  knowledgeBaseId: string;
  title: string;
  format: string; // 受支持来源格式：docx/pptx/xlsx/pdf/md/txt/png/jpg/jpeg
  ingestionStatus: IngestionStatus;
  chunkCount: number;
  sizeBytes: number;
  createdAt: string;
}

/** 分块（文档中可独立索引与引证的结构感知片段）。 */
export interface Chunk {
  id: string;
  documentId: string;
  content: string;
  pageRef?: string; // 页面/区域引用
  headings?: string[]; // 结构上下文（标题链）
  tokenCount: number;
  createdAt: string;
}

/** 摄取运行（异步、可观测，把文档转成分块与已发布版本）。 */
export interface IngestionStage {
  name: string;
  label: string; // 阶段显示名（中文）
  status: StageStatus;
}

export interface IngestionRun {
  id: string;
  documentTitle: string;
  status: IngestionStatus;
  stages: IngestionStage[];
  startedAt: string;
}

/** 意图树节点（配置的信息操作或系统动作）。 */
export interface IntentNode {
  id: string;
  name: string; // 节点名（正名）
  description?: string;
  parentId: string | null;
  level: number;
  kind: string; // leaf / system / guidance…
  enabled: boolean;
  examples: string[];
  safetyScope?: string; // 安全边界适用范围（治疗/药物/诊断/急症…）
}

/** 查询术语映射（术语 → 意图节点）。 */
export interface QueryTermMapping {
  id: string;
  term: string;
  intentNodeId: string;
  enabled: boolean;
  createdAt: string;
}

/** 模型目标（配置的模型提供方与能力集）。 */
export interface ModelTarget {
  id: string;
  name: string;
  provider: string; // Generation/Embedding/Reranker
  model: string;
  capabilities: string[];
  status: "healthy" | "degraded" | "unreachable";
  credentialBound: boolean;
  circuitState: "closed" | "open" | "half-open";
}

/** 平台模型凭据（操作者管理，不成为工作区数据）。 */
export interface PlatformCredential {
  id: string;
  providerName: string;
  boundTargetId: string;
  lastTestedAt?: string;
  lastTestResult: "ok" | "fail" | "untested";
}

/** 业务运行记录（追踪：PostgreSQL 权威生命周期，观测后端仅承载 AI/RAG 详情）。 */
export interface RunRecord {
  id: string;
  runId: string;
  conversationId?: string;
  question: string;
  outcome: RunOutcome;
  latencyMs: number;
  traceId?: string;
  createdAt: string;
}

/** 用户（经过鉴权的个人账户，可属于一个或多个工作区）。 */
export interface User {
  id: string;
  email: string;
  role: "member" | "admin";
  status: "active" | "disabled";
  createdAt: string;
}

/** 工作区（成员共享知识库/会话/运营记录的隔离范围）。 */
export interface Workspace {
  id: string;
  name: string;
  memberCount: number;
  createdAt: string;
}

/** 审计事件 / 操作变更日志。 */
export interface AuditEvent {
  id: string;
  actorEmail: string;
  action: string;
  entityType: string;
  entityName: string;
  detail: string;
  createdAt: string;
}

/** 样例问题（推荐问题配置）。 */
export interface SampleQuestion {
  id: string;
  text: string;
  enabled: boolean;
  createdAt: string;
}

/** 反馈审核条目（对回答的反馈）。 */
export interface FeedbackItem {
  id: string;
  messageId: string;
  conversationId?: string;
  value: "like" | "dislike";
  comment?: string;
  createdAt: string;
}

/** 仪表盘 KPI 面板（摄取/聊天/模型/检索指标）。 */
export interface DashboardMetrics {
  totalChats: number;
  totalQuestions: number;
  avgLatencyMs: number;
  publishedDocs: number;
  failedRuns: number;
  activeModelTargets: number;
  degradedModelTargets: number;
  questionTrend: TrendPoint[];
  ingestionTrend: TrendPoint[];
  modelTargets: ModelTarget[];
  recentRuns: RunRecord[];
}

export interface TrendPoint {
  date: string; // yyyy-mm-dd
  value: number;
}

/** 服务健康检查（/ready 运行时形状；契约补齐响应模型后替换为生成类型）。 */
export interface HealthStatus {
  status: "healthy" | "degraded";
  checks: Record<string, string>;
}