// 服务端状态查询（development-standards §服务端状态：TanStack Query + useSuspenseQuery/
// ensureQueryData，不手写 fetch 缓存）。queryOptions 供 loader 与组件复用同一 queryKey。
import { queryOptions, useQuery } from "@tanstack/react-query";
import {
  ApiError,
  fetchChunks,
  fetchConversations,
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
  fetchRun,
  fetchRuns,
  fetchSampleQuestions,
  fetchUsers,
  fetchWorkspaces,
  type UserOut,
} from "./api";

export const authKeys = {
  all: ["auth"] as const,
  me: ["auth", "me"] as const,
};

export function meQueryOptions() {
  return queryOptions({
    queryKey: authKeys.me,
    // 未登录（401）是正常状态，归一为 null；网络/5xx 必须上抛，
    // 否则鉴权守卫会把服务故障当成“未登录”并静默踢到登录页。
    queryFn: async (): Promise<UserOut | null> => {
      try {
        return await fetchMe();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
  });
}

/** 会话列表（聊天侧栏与线程适配器共用，避免内联 queryKey 造成缓存碎片）。 */
export function conversationsQueryOptions() {
  return queryOptions({
    queryKey: ["conversations"] as const,
    queryFn: fetchConversations,
    staleTime: 30_000,
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
  knowledgeBases: ["admin", "knowledge-bases"] as const,
  documents: (kbId: string) => ["admin", "documents", kbId] as const,
  chunks: (docId: string) => ["admin", "chunks", docId] as const,
  ingestion: ["admin", "ingestion"] as const,
  intentTree: ["admin", "intent-tree"] as const,
  mappings: ["admin", "mappings"] as const,
  models: ["admin", "models"] as const,
  runs: ["admin", "runs"] as const,
  run: (id: string) => ["admin", "runs", id] as const,
  users: ["admin", "users"] as const,
  workspaces: ["admin", "workspaces"] as const,
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

export function runsQueryOptions() {
  return queryOptions({ queryKey: adminKeys.runs, queryFn: fetchRuns });
}

export function runQueryOptions(id: string) {
  return queryOptions({ queryKey: adminKeys.run(id), queryFn: () => fetchRun(id) });
}

export function usersQueryOptions() {
  return queryOptions({ queryKey: adminKeys.users, queryFn: fetchUsers });
}

export function workspacesQueryOptions() {
  return queryOptions({ queryKey: adminKeys.workspaces, queryFn: fetchWorkspaces });
}

export function sampleQuestionsQueryOptions() {
  // 欢迎屏样例问题：用户侧 /api/sample-questions（无管理端写路径，migration seed）
  return queryOptions({ queryKey: ["sample-questions"], queryFn: fetchSampleQuestions });
}

export function feedbackQueryOptions() {
  return queryOptions({ queryKey: adminKeys.feedback, queryFn: fetchFeedback });
}
