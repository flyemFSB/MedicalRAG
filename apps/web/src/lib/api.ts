// 类型化 API 请求层（openapi-typescript 生成类型；TanStack Query 拥有请求层）。
// 后端运营端点已落地：全部经真实 fetch（同源 /api 由 dev Vite proxy / prod Nginx 反代）。
// 响应为 snake_case（OpenAPI 契约），在此映射为前端 camelCase 领域类型（lib/types.ts）。
import type { components } from "../api/schema";
import type {
  Chunk,
  DashboardMetrics,
  Document,
  FeedbackItem,
  HealthStatus,
  IngestionRun,
  IntentNode,
  KnowledgeBase,
  ModelTarget,
  QueryTermMapping,
  RunRecord,
  SampleQuestion,
  StageStatus,
  User,
} from "./types";

type schemas = components["schemas"];
type DashboardRaw = schemas["DashboardOut"];
type KnowledgeBaseRaw = schemas["KnowledgeBaseOut"];
type DocumentRaw = schemas["DocumentOut"];
type ChunkRaw = schemas["ChunkOut"];
type IntentNodeRaw = schemas["IntentNodeOut"];
type IngestionRunRaw = schemas["IngestionRunOut"];
type MappingRaw = schemas["MappingOut"];
type ModelTargetRaw = schemas["ModelTargetOut"];
type TraceRaw = schemas["TraceOut"];
type UserRaw = schemas["medicalrag_api__api__admin__UserOut"];
type WorkspaceRaw = schemas["WorkspaceOut"];
type FeedbackRaw = schemas["FeedbackOut"];

type Credentials = schemas["Credentials"];
// 认证用户契约（含 role，供前端权限门禁与 Topbar 条件渲染）直接来自 OpenAPI 生成类型
export type UserOut = schemas["medicalrag_api__api__auth__UserOut"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`API 请求失败（HTTP ${status}）`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return (await response.json()) as T;
}

// --- 认证 ---
export function register(body: Credentials): Promise<UserOut> {
  return apiFetch<UserOut>("/api/auth/register", { method: "POST", body: JSON.stringify(body) });
}

export function login(body: Credentials): Promise<UserOut> {
  return apiFetch<UserOut>("/api/auth/login", { method: "POST", body: JSON.stringify(body) });
}

export function fetchMe(): Promise<UserOut> {
  return apiFetch<UserOut>("/api/auth/me");
}

export function logout(): Promise<unknown> {
  return apiFetch<unknown>("/api/auth/logout", { method: "POST" });
}

export function fetchHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/ready");
}

// --- 聊天（生产前端经 Aegra v2 /api/agent 官方 useStreamRuntime 消费，见 screens/ChatScreen.tsx） ---

export interface ChatEvidenceOut {
  chunk_id: string;
  source_id: string;
  title: string;
  snippet: string;
  citation_label: string;
  score: number;
}

// --- 仪表盘 ---

export async function fetchDashboard(): Promise<DashboardMetrics> {
  const raw = await apiFetch<DashboardRaw>("/api/admin/dashboard");
  return {
    totalChats: raw.total_chats,
    totalQuestions: raw.total_questions,
    avgLatencyMs: raw.avg_latency_ms,
    publishedDocs: raw.published_docs,
    failedRuns: raw.failed_runs,
    activeModelTargets: raw.active_model_targets,
    degradedModelTargets: raw.degraded_model_targets,
  };
}

// --- 知识库 ---

function kb(raw: KnowledgeBaseRaw): KnowledgeBase {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    documentCount: raw.document_count,
    createdAt: raw.created_at ?? "",
    updatedAt: raw.updated_at ?? "",
  };
}

export async function fetchKnowledgeBases(): Promise<KnowledgeBase[]> {
  const rows = await apiFetch<KnowledgeBaseRaw[]>("/api/admin/knowledge-bases");
  return rows.map(kb);
}

export function createKnowledgeBase(input: {
  name: string;
  description: string;
}): Promise<KnowledgeBase> {
  return apiFetch<KnowledgeBaseRaw>("/api/admin/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(input),
  }).then(kb);
}

// --- 文档 ---

function doc(raw: DocumentRaw): Document {
  return {
    id: raw.id,
    knowledgeBaseId: raw.knowledge_base_id,
    title: raw.title,
    format: raw.format,
    ingestionStatus: raw.ingestion_status as Document["ingestionStatus"],
    chunkCount: raw.chunk_count,
    sizeBytes: raw.size_bytes,
    createdAt: raw.created_at ?? "",
  };
}

export async function fetchDocuments(knowledgeBaseId: string): Promise<Document[]> {
  const rows = await apiFetch<DocumentRaw[]>(
    `/api/admin/knowledge-bases/${knowledgeBaseId}/documents`,
  );
  return rows.map(doc);
}

// --- 分块 ---

export async function fetchChunks(documentId: string): Promise<Chunk[]> {
  const rows = await apiFetch<ChunkRaw[]>(`/api/admin/documents/${documentId}/chunks`);
  return rows.map((r) => ({
    id: r.id,
    documentId: r.document_id,
    content: r.content,
    pageRef: r.page_ref ?? undefined,
    headings: r.headings,
    tokenCount: r.token_count,
    createdAt: r.created_at ?? "",
  }));
}

// --- 摄取运行 ---
export async function fetchIngestionRuns(): Promise<IngestionRun[]> {
  const rows = await apiFetch<IngestionRunRaw[]>(`/api/admin/ingestion-runs`);
  return rows.map((r) => ({
    id: r.id,
    documentTitle: r.document_title,
    status: r.status as IngestionRun["status"],
    stages: r.stages.map((s: Record<string, string>) => ({
      name: s.name,
      label: s.label,
      status: s.status as StageStatus,
    })),
    startedAt: r.started_at ?? "",
  }));
}

export function retryIngestionRun(id: string): Promise<void> {
  return apiFetch<void>(`/api/admin/ingestion-runs/${id}/retry`, { method: "POST" });
}

// --- 意图树 ---

export async function fetchIntentTree(): Promise<IntentNode[]> {
  const rows = await apiFetch<IntentNodeRaw[]>("/api/admin/intent-tree");
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    description: r.description,
    parentId: r.parent_id,
    level: r.level === "domain" ? 0 : 1,
    kind: r.kind,
    enabled: r.enabled,
    examples: r.examples,
    safetyScope: r.safety_scope ?? undefined,
  }));
}

export function updateIntentNode(id: string, patch: Partial<IntentNode>): Promise<void> {
  const body: Record<string, unknown> = {};
  if (patch.name !== undefined) body.name = patch.name;
  if (patch.description !== undefined) body.description = patch.description;
  if (patch.examples !== undefined) body.examples = patch.examples;
  if (patch.enabled !== undefined) body.enabled = patch.enabled;
  if (patch.safetyScope !== undefined) body.safety_scope = patch.safetyScope;
  if (patch.parentId !== undefined) body.parent_id = patch.parentId;
  if (patch.kind !== undefined) body.kind = patch.kind;
  return apiFetch<void>(`/api/admin/intent-tree/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- 查询术语映射 ---
export async function fetchMappings(): Promise<QueryTermMapping[]> {
  const rows = await apiFetch<MappingRaw[]>("/api/admin/query-term-mappings");
  return rows.map((r) => ({
    id: r.id,
    term: r.term,
    intentNodeId: r.intent_node_id,
    createdAt: r.created_at ?? "",
  }));
}

export function createMapping(input: { term: string; intentNodeId: string }): Promise<void> {
  return apiFetch<void>("/api/admin/query-term-mappings", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// --- 模型目标 ---
export async function fetchModelTargets(): Promise<ModelTarget[]> {
  const rows = await apiFetch<ModelTargetRaw[]>("/api/admin/model-targets");
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    provider: r.provider,
    model: r.model,
    capabilities: r.capabilities ?? [],
    status: r.status as ModelTarget["status"],
    circuitState: r.circuit_state as ModelTarget["circuitState"],
  }));
}

// --- 追踪 ---
function mapTrace(r: TraceRaw): RunRecord {
  return {
    // 后端 TraceOut 仅含 run_id；id 保留为运行记录在 UI 表格中的稳定键
    id: r.run_id,
    runId: r.run_id,
    conversationId: r.conversation_id,
    question: r.question,
    outcome: r.outcome as RunRecord["outcome"],
    latencyMs: r.latency_ms,
    traceId: r.trace_id ?? undefined,
    createdAt: r.created_at ?? "",
  };
}

export async function fetchRuns(): Promise<RunRecord[]> {
  const rows = await apiFetch<TraceRaw[]>("/api/admin/traces");
  return rows.map(mapTrace);
}

/** 单条运行详情：直接命中详情端点，不在前端拉全表再 find（列表截断会误报“未找到”）。 */
export async function fetchRun(runId: string): Promise<RunRecord | null> {
  try {
    return mapTrace(await apiFetch<TraceRaw>(`/api/admin/traces/${encodeURIComponent(runId)}`));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

// --- 用户 / 工作区 ---
export async function fetchUsers(): Promise<User[]> {
  const rows = await apiFetch<UserRaw[]>("/api/admin/users");
  return rows.map((r) => ({
    id: r.id,
    email: r.email,
    createdAt: r.created_at ?? "",
  }));
}

export async function fetchWorkspaces(): Promise<import("./types").Workspace[]> {
  const rows = await apiFetch<WorkspaceRaw[]>("/api/admin/workspaces");
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    memberCount: r.member_count,
    createdAt: r.created_at ?? "",
  }));
}

// --- 样例问题 ---
export async function fetchSampleQuestions(): Promise<SampleQuestion[]> {
  // 用户侧端点（/api/sample-questions）：服务端只回已启用项（SampleQuestionPublic），全体登录用户可见
  const rows = await apiFetch<schemas["SampleQuestionPublic"][]>("/api/sample-questions");
  return rows.map((r) => ({ id: r.id, text: r.text }));
}

// --- 反馈 ---
export async function fetchFeedback(): Promise<FeedbackItem[]> {
  const rows = await apiFetch<FeedbackRaw[]>("/api/admin/feedback");
  return rows.map((r) => ({
    id: r.id,
    messageId: r.message_id,
    conversationId: r.conversation_id,
    value: r.value as FeedbackItem["value"],
    comment: r.comment ?? undefined,
    createdAt: r.created_at ?? "",
  }));
}

// --- 会话（用户侧；契约类型直接复用 OpenAPI 生成物，不手写重复 DTO） ---
export type ConversationOut = schemas["ConversationOut"];

export async function fetchConversations(): Promise<ConversationOut[]> {
  return apiFetch<ConversationOut[]>("/api/conversations");
}

export function createConversation(title = "新会话"): Promise<ConversationOut> {
  return apiFetch<ConversationOut>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

// --- 反馈提交（用户侧） ---
export function submitFeedback(body: schemas["FeedbackIn"]): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
