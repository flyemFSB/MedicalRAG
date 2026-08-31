// 服务端状态查询（development-standards §服务端状态：TanStack Query + useSuspenseQuery/
// ensureQueryData，不手写 fetch 缓存）。queryOptions 供 loader 与组件复用同一 queryKey。
import { queryOptions, useQuery } from "@tanstack/react-query";
import {
  createKnowledgeBase,
  fetchAuditEvents,
  fetchChunks,
  fetchCredentials,
  fetchDashboard,
  fetchDocuments,
  fetchFeedback,
  fetchHealth,
  fetchIngestionRuns,
  fetchIntentTree,
  fetchKnowledgeBases,
  fetchMappings,
  fetchMe,
  fetchModelTargets,
  fetchRuns,
  fetchSampleQuestions,
  fetchUsers,
  fetchWorkspaces,
  retryIngestionRun,
  updateIntentNode,
  createMapping,
} from "./api";

export const authKeys = {
  all: ["auth"] as const,
  me: ["auth", "me"] as const,
};

export function meQueryOptions() {
  return queryOptions({
    queryKey: authKeys.me,
    queryFn: fetchMe,
    // 未登录时 /api/auth/me 返回 401，属正常状态而非请求失败。
    retry: false,
  });
}

export function healthQueryOptions() {
  return queryOptions({
    queryKey: ["health", "ready"],
    queryFn: fetchHealth,
    refetchInterval: 15_000,
  });
}

/** 当前登录用户；401（未登录）不视为错误，仅 isAuthenticated=false。 */
export function useCurrentUser() {
  const query = useQuery(meQueryOptions());
  return { user: query.data, isPending: query.isPending, isAuthenticated: query.data != null };
}

// --- 运营控制台各模块 query options（loader/组件共用同一 queryKey） ---

export function dashboardQueryOptions() {
  return queryOptions({ queryKey: ["dashboard"], queryFn: fetchDashboard });
}

export const adminKeys = {
  all: ["admin"] as const,
  knowledgeBases: ["admin", "knowledge-bases"] as const,
  documents: (kbId: string) => ["admin", "documents", kbId] as const,
  chunks: (docId: string) => ["admin", "chunks", docId] as const,
  ingestion: ["admin", "ingestion"] as const,
  intentTree: ["admin", "intent-tree"] as const,
  mappings: ["admin", "mappings"] as const,
  models: ["admin", "models"] as const,
  credentials: ["admin", "credentials"] as const,
  runs: ["admin", "runs"] as const,
  run: (id: string) => ["admin", "runs", id] as const,
  users: ["admin", "users"] as const,
  workspaces: ["admin", "workspaces"] as const,
  audit: ["admin", "audit"] as const,
  sampleQuestions: ["admin", "sample-questions"] as const,
  feedback: ["admin", "feedback"] as const,
};

export function knowledgeBasesQueryOptions() {
  return queryOptions({ queryKey: adminKeys.knowledgeBases, queryFn: fetchKnowledgeBases });
}

export function documentsQueryOptions(kbId: string) {
  return queryOptions({ queryKey: adminKeys.documents(kbId), queryFn: () => fetchDocuments(kbId) });
}

export function chunksQueryOptions(docId: string) {
  return queryOptions({ queryKey: adminKeys.chunks(docId), queryFn: () => fetchChunks(docId) });
}

export function ingestionRunsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.ingestion, queryFn: fetchIngestionRuns });
}

export function intentTreeQueryOptions() {
  return queryOptions({ queryKey: adminKeys.intentTree, queryFn: fetchIntentTree });
}

export function mappingsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.mappings, queryFn: fetchMappings });
}

export function modelTargetsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.models, queryFn: fetchModelTargets });
}

export function credentialsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.credentials, queryFn: fetchCredentials });
}

export function runsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.runs, queryFn: fetchRuns });
}

export function runQueryOptions(id: string) {
  return queryOptions({
    queryKey: adminKeys.run(id),
    queryFn: () => fetchRuns().then((r) => r.find((x) => x.id === id) ?? null),
  });
}

export function usersQueryOptions() {
  return queryOptions({ queryKey: adminKeys.users, queryFn: fetchUsers });
}

export function workspacesQueryOptions() {
  return queryOptions({ queryKey: adminKeys.workspaces, queryFn: fetchWorkspaces });
}

export function auditQueryOptions() {
  return queryOptions({ queryKey: adminKeys.audit, queryFn: fetchAuditEvents });
}

export function sampleQuestionsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.sampleQuestions, queryFn: fetchSampleQuestions });
}

export function feedbackQueryOptions() {
  return queryOptions({ queryKey: adminKeys.feedback, queryFn: fetchFeedback });
}

export const adminMutations = {
  createKnowledgeBase,
  retryIngestionRun,
  updateIntentNode,
  createMapping,
};
