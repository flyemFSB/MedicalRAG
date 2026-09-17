// 聊天工作台（证据优先三栏：会话侧栏 + 消息线程/输入 + 证据面板）。
//
// 约束（用户钉死）：agent 部分只用 assistant-ui 内置组件 —— Thread 及其 Welcome 槽、
// 消息/输入/操作条全部由内置 Thread 渲染；其余（会话栏、证据面板、安全边界、反馈、
// 移动端抽屉）只用 shadcn base-ui 组件在屏幕内组合，无自定义组件。
//
// 聊天运行时：assistant-ui 官方 @assistant-ui/react-langgraph 桥（useLangGraphRuntime +
// unstable_createLangGraphStream），stream 由调用方实现 —— SDK client 直连 Aegra
// （LangGraph Platform 兼容，Agent Protocol v2 SSE，/api/agent 同源反代）。
// 自托管线程适配器（unstable_threadListAdapter）：会话列表/新建/切换全部对接后端业务会话
// （PostgreSQL Conversation.id == Aegra thread_id），适配器 initialize 在新会话首次发送时
// 建业务行（后端定 id）；load 在切换会话时经 getState 回读历史；onThreadIdChange 回写
// 当前会话 id 供侧栏高亮。取消经官方 Cancel 按钮 → abortSignal（unstable_allowCancellation）。
// 未提供 getCheckpointId：内置 Thread 的编辑/重跑按钮安全禁用（B 侧图亦无 fork 语义）。
import { AssistantRuntimeProvider, type AssistantRuntime } from "@assistant-ui/react";
import {
  unstable_createLangGraphStream,
  useLangGraphRuntime,
  useLangGraphState,
  type LangChainMessage,
} from "@assistant-ui/react-langgraph";
import { Client } from "@langchain/langgraph-sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, MessageSquare, Plus, ShieldAlert, ThumbsDown, ThumbsUp } from "lucide-react";
import {
  useCallback,
  useMemo,
  useRef,
  useSyncExternalStore,
  useState,
  type ComponentType,
} from "react";
import { toast } from "sonner";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { ScrollArea } from "../components/ui/scroll-area";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "../components/ui/sheet";
import { Thread } from "../components/assistant-ui/elements/thread.aui";
import {
  createConversation,
  fetchConversations,
  submitFeedback,
  type ChatEvidenceOut,
  type ConversationOut,
} from "../lib/api";
import { conversationsQueryOptions, sampleQuestionsQueryOptions } from "../lib/queries";
import { relativeTime } from "../lib/format";
import { cn } from "../lib/utils";

/** 助手消息元数据：图经 AIMessage.additional_kwargs["custom"] 写出，assistant-ui 官方桥透传为消息 metadata.custom。 */
export type AssistantMeta = {
  evidence?: ChatEvidenceOut[];
  safety?: { risk_class?: string; scope_notice?: string | null; escalation?: string | null };
  outcome?: string;
} & Record<string, unknown>;

export interface SessionEntry {
  id: string;
  title: string;
  lastTime: string;
}

/** Aegra（LangGraph Platform 兼容）SDK 客户端：经同源 /api/agent 反向代理，前缀由代理剥离。
 *  API 地址必须是绝对 URL：SDK 内部以 `new URL(apiUrl + path)` 构造请求，相对串会直接抛 TypeError。 */
const agentClient = new Client({ apiUrl: new URL("/api/agent", window.location.origin).href });

type ThreadMessages = ReturnType<AssistantRuntime["thread"]["getState"]>["messages"];

/** 仅订阅线程消息的最小快照（流式 token 只重渲染订阅者，不重渲染整屏三栏布局）。 */
function useThreadMessages(runtime: AssistantRuntime): ThreadMessages {
  const subscribe = useCallback(
    (callback: () => void) => runtime.thread.subscribe(callback),
    [runtime],
  );
  return useSyncExternalStore(subscribe, () => runtime.thread.getState().messages);
}

function latestSafety(messages: ThreadMessages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role !== "assistant") continue;
    const meta = (message.metadata?.custom ?? {}) as Partial<AssistantMeta>;
    if (meta.safety?.scope_notice) return meta.safety;
  }
  return undefined;
}

function latestCompletedAssistantId(messages: ThreadMessages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === "assistant" && message.status.type === "complete") return message.id;
  }
  return undefined;
}

/** Aegra 对“线程尚未创建”返回 404；SDK 未导出统一错误类型，故按 status / 文案兼容判定。 */
function isNotFound(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return status === 404 || (error instanceof Error && /\b404\b/.test(error.message));
}

export function ChatScreen() {
  const queryClient = useQueryClient();
  // 会话列表必须区分加载/错误/空三态：请求失败渲染成“还没有会话”是假空态（医疗证据界面不允许）
  const {
    data: backendSessions,
    isPending: sessionsLoading,
    isError: sessionsError,
    refetch,
  } = useQuery(conversationsQueryOptions());
  const sessions: SessionEntry[] = (backendSessions ?? []).map((c) => ({
    id: c.id,
    title: c.title,
    lastTime: c.updated_at ?? "",
  }));

  const [activeId, setActiveId] = useState<string | null>(null);

  // 自托管线程适配器：会话列表/新建/切换全部对接后端业务会话（Conversation.id == Aegra thread_id）。
  // list/fetch 供运行时识别可切换的线程；initialize 在新会话首次发送时建业务行（后端定 id）。
  const toThread = (c: ConversationOut) => ({
    status: "regular" as const,
    remoteId: c.id,
    externalId: c.id,
    title: c.title,
    lastMessageAt: c.updated_at ? new Date(c.updated_at) : undefined,
  });
  const threadListAdapter = useMemo(
    () => ({
      list: async () => ({ threads: (await fetchConversations()).map(toThread) }),
      fetch: async (id: string) => {
        const c = (await fetchConversations()).find((x) => x.id === id);
        if (!c) throw new Error(`会话不存在：${id}`);
        return toThread(c);
      },
      initialize: async () => {
        const conversation = await createConversation();
        queryClient.invalidateQueries({ queryKey: conversationsQueryOptions().queryKey });
        return { remoteId: conversation.id, externalId: conversation.id };
      },
      // 侧栏自绘且无重命名/归档/删除 UI；这些动作不会被触发，保持空实现即可。
      rename: async () => {},
      archive: async () => {},
      unarchive: async () => {},
      delete: async () => {},
      generateTitle: async () => {
        throw new Error("标题生成未接入");
      },
    }),
    [queryClient],
  );

  // 官方 LangGraph 桥（react-langgraph）：stream 由调用方实现（SDK client 直连 SSE），
  // 会话优先语义经线程适配器承载；取消经官方 Cancel 按钮 → abortSignal。
  const runtime: AssistantRuntime = useLangGraphRuntime({
    threadId: activeId ?? undefined,
    // 必须显式包含 values：useLangGraphState（证据面板）只从 values 通道取图状态，
    // 默认 streamMode 不含 values，证据栏会永远为空。
    stream: unstable_createLangGraphStream({
      client: agentClient,
      assistantId: "agent",
      streamMode: ["messages", "updates", "custom", "values"],
    }),
    unstable_allowCancellation: true,
    unstable_threadListAdapter: threadListAdapter,
    load: async (threadId) => {
      try {
        const state = await agentClient.threads.getState<{ messages: LangChainMessage[] }>(
          threadId,
        );
        return { messages: state.values.messages ?? [] };
      } catch (error) {
        // 会话存在但 Aegra 线程尚未创建（从未跑过 run）时服务端返回 404，按空历史处理；
        // 其余错误必须上抛，否则会把鉴权/故障伪装成“空历史”。
        if (isNotFound(error)) return { messages: [] };
        throw error;
      }
    },
    onThreadIdChange: (id) => setActiveId(id ?? null),
  });

  const handleSelectSession = (id: string) => {
    setActiveId(id);
  };

  const feedbackMutation = useMutation({
    mutationFn: (input: { messageId: string; value: "like" | "dislike" }) =>
      submitFeedback({
        message_id: input.messageId,
        conversation_id: activeId ?? "",
        value: input.value,
      }),
    onError: () => toast.error("反馈提交失败，请稍后重试"),
  });

  const handleFeedback = (messageId: string, value: "like" | "dislike" | null) => {
    if (!value) return;
    if (!activeId) {
      toast.error("请先完成一轮对话再评价");
      return;
    }
    feedbackMutation.mutate({ messageId, value });
  };

  // Welcome 槽适配器：闭包经 ref 传递，身份终身稳定（不随渲染重挂载）
  const askRef = useRef<(text: string) => void>(() => {});
  askRef.current = (text: string) => {
    void runtime.thread.append({ role: "user", content: [{ type: "text", text }] });
  };
  const Welcome = useMemo(
    () => () => <ChatWelcomeContent onAsk={(text) => askRef.current(text)} />,
    [],
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatLayout
        runtime={runtime}
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        sessionsError={sessionsError}
        activeId={activeId}
        Welcome={Welcome}
        onNewSession={() => {
          setActiveId(null);
          void refetch();
        }}
        onSelectSession={handleSelectSession}
        onFeedback={handleFeedback}
      />
    </AssistantRuntimeProvider>
  );
}

function ChatLayout({
  runtime,
  sessions,
  sessionsLoading,
  sessionsError,
  activeId,
  Welcome,
  onNewSession,
  onSelectSession,
  onFeedback,
}: {
  runtime: AssistantRuntime;
  sessions: SessionEntry[];
  sessionsLoading: boolean;
  sessionsError: boolean;
  activeId: string | null;
  Welcome: ComponentType;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
}) {
  const graphState = useLangGraphState<{ evidence?: ChatEvidenceOut[] }>();
  const evidence = graphState?.evidence ?? [];
  const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);
  const activeTitle = sessions.find((s) => s.id === activeId)?.title;

  return (
    <div className="flex min-h-0 flex-1 gap-0 overflow-hidden text-foreground">
      <SessionSidebar
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        sessionsError={sessionsError}
        activeId={activeId}
        onSelect={onSelectSession}
        onNew={onNewSession}
      />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border/60 bg-surface px-3 py-2 min-[860px]:hidden">
          <Sheet open={mobileSessionsOpen} onOpenChange={setMobileSessionsOpen}>
            <SheetTrigger
              render={
                <Button variant="ghost" size="sm" className="gap-1.5 rounded-lg">
                  <MessageSquare className="size-4" aria-hidden />
                  会话
                </Button>
              }
            />
            <SheetContent side="left" className="w-72 gap-0 p-0 rounded-r-2xl">
              <SheetTitle className="sr-only">会话</SheetTitle>
              <SessionListBody
                sessions={sessions}
                sessionsLoading={sessionsLoading}
                sessionsError={sessionsError}
                activeId={activeId}
                onSelect={(id) => {
                  setMobileSessionsOpen(false);
                  onSelectSession(id);
                }}
                onNew={() => {
                  setMobileSessionsOpen(false);
                  onNewSession();
                }}
              />
            </SheetContent>
          </Sheet>
          <span className="truncate text-body-sm text-muted-foreground">
            {activeTitle ?? "证据优先 · 循证问答"}
          </span>
        </div>

        <SafetyBanner runtime={runtime} />

        <div className="min-h-0 flex-1">
          <div className="h-full">
            <Thread Welcome={Welcome} />
          </div>
        </div>

        {/* 固定免责声明（ADR 0042）：加载/流式/错误/空证据态恒可见，不由模型生成 */}
        <p className="border-t border-border/60 bg-panel/20 px-4 py-2 text-center text-caption text-muted-foreground">
          AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准
        </p>
      </section>

      <EvidenceSidebar evidence={evidence} runtime={runtime} onFeedback={onFeedback} />
    </div>
  );
}

/** 安全边界横幅：自订阅线程消息，避免流式 token 重渲染整个三栏布局。 */
function SafetyBanner({ runtime }: { runtime: AssistantRuntime }) {
  const messages = useThreadMessages(runtime);
  const safety = useMemo(() => latestSafety(messages), [messages]);
  if (!safety) return null;
  return (
    <div className="px-4 pt-3.5">
      <div
        role="alert"
        className="safety-band mx-auto flex max-w-[44rem] items-start gap-2.5 rounded-xl px-3.5 py-3 shadow-xs"
      >
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-medical-strong" aria-hidden />
        <div className="min-w-0">
          <p className="text-body-sm font-semibold text-safety-ink">安全边界</p>
          <p className="mt-0.5 text-body-sm leading-relaxed text-safety-ink/90">
            {safety.scope_notice}
            {safety.escalation ? ` ${safety.escalation}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

/** 欢迎屏（Thread 的内置 Welcome 槽）：shadcn 组件 + 官方 append 路径，无自定义样式组件。 */
function ChatWelcomeContent({ onAsk }: { onAsk: (text: string) => void }) {
  const { data: questions = [] } = useQuery(sampleQuestionsQueryOptions());
  const suggestions = questions.slice(0, 4);

  return (
    <div className="w-full max-w-lg px-4 py-10 text-center">
      <h1 className="font-display text-display text-ink text-balance tracking-tight">
        每个答案，都有据可查。
      </h1>
      <p className="mx-auto mt-3 max-w-[46ch] text-body-sm leading-relaxed text-muted-foreground">
        面向医疗来源的循证问答：检索知识库、标注证据来源，并在涉及治疗、用药或急症时明确安全边界。
      </p>
      {suggestions.length > 0 ? (
        <div className="mt-8">
          <p className="mb-2.5 text-left font-mono text-metadata font-medium tracking-wide text-faint uppercase">
            试着问
          </p>
          <div className="flex flex-col gap-1.5">
            {suggestions.map((q) => (
              <Button
                key={q.id}
                type="button"
                variant="ghost"
                className="h-auto justify-between gap-3 rounded-xl border border-border/70 bg-surface px-3.5 py-2.5 text-left font-normal transition-all hover:bg-panel/70 active:scale-[0.99]"
                onClick={() => onAsk(q.text)}
              >
                <span className="text-left text-caption text-ink">{q.text}</span>
                <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              </Button>
            ))}
          </div>
        </div>
      ) : null}
      <p className="mt-8 flex items-center justify-center gap-2 text-caption text-muted-foreground">
        <span className="size-1.5 rounded-full bg-medical" aria-hidden />
        涉及治疗 / 用药 / 急症时，会先展示安全边界。
      </p>
    </div>
  );
}

/** 会话侧栏（桌面）+ 移动端抽屉共用主体：shadcn base-ui 组合。 */
function SessionSidebar({
  sessions,
  sessionsLoading,
  sessionsError,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: SessionEntry[];
  sessionsLoading: boolean;
  sessionsError: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <nav
      aria-label="会话列表"
      className="hidden w-64 shrink-0 flex-col border-r border-border/70 bg-panel/30 overflow-hidden min-[860px]:flex"
    >
      <SessionListBody
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        sessionsError={sessionsError}
        activeId={activeId}
        onSelect={onSelect}
        onNew={onNew}
      />
    </nav>
  );
}

function SessionListBody({
  sessions,
  sessionsLoading,
  sessionsError,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: SessionEntry[];
  sessionsLoading: boolean;
  sessionsError: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-border/50 px-3.5 py-2.5">
        <h2 className="text-body-sm font-semibold tracking-tight text-ink">会话</h2>
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1 rounded-lg border-border/70 bg-panel/50 px-2 text-caption text-ink hover:bg-panel"
          onClick={onNew}
        >
          <Plus className="size-3.5" aria-hidden />
          新建
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-1 p-2">
          {sessionsError ? (
            <p role="alert" className="px-3 py-2 text-caption text-destructive">
              会话加载失败，请点击「新建」或刷新页面重试
            </p>
          ) : sessionsLoading ? (
            <p aria-busy="true" className="px-3 py-2 text-caption text-muted-foreground">
              会话加载中…
            </p>
          ) : sessions.length === 0 ? (
            <p className="px-3 py-2 text-caption text-muted-foreground">还没有会话</p>
          ) : (
            sessions.map((session) => {
              const active = session.id === activeId;
              return (
                <Button
                  key={session.id}
                  type="button"
                  variant="ghost"
                  className={cn(
                    "group h-auto justify-start gap-2.5 rounded-xl px-2.5 py-2 text-left font-normal transition-all active:scale-[0.99]",
                    active
                      ? "bg-panel text-ink shadow-xs ring-1 ring-border/60 hover:bg-panel hover:text-ink"
                      : "text-muted-foreground hover:bg-panel/60 hover:text-ink",
                  )}
                  onClick={() => onSelect(session.id)}
                >
                  <MessageSquare
                    className={cn(
                      "size-3.5 shrink-0 transition-colors",
                      active ? "text-accent-ink" : "text-muted-foreground group-hover:text-ink",
                    )}
                    aria-hidden
                  />
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-caption",
                      active ? "font-semibold text-ink" : "font-normal",
                    )}
                  >
                    {session.title}
                  </span>
                  <span className="shrink-0 text-metadata text-faint">
                    {relativeTime(session.lastTime)}
                  </span>
                </Button>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

/** 证据面板（右栏）：shadcn base-ui 组合（Card/Badge），无自定义组件。 */
function EvidenceSidebar({
  evidence,
  runtime,
  onFeedback,
}: {
  evidence: ChatEvidenceOut[];
  runtime: AssistantRuntime;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
}) {
  return (
    <aside
      aria-label="证据面板"
      className="hidden w-72 shrink-0 flex-col border-l border-border/70 bg-panel/20 overflow-hidden min-[1080px]:flex"
    >
      <div className="flex items-center justify-between border-b border-border/50 px-3.5 py-2.5">
        <h2 className="text-body-sm font-semibold tracking-tight text-ink">证据</h2>
        {evidence.length > 0 ? (
          <Badge
            variant="outline"
            className="rounded-lg border-border/60 bg-panel/60 px-1.5 py-0 text-metadata font-medium text-muted-foreground"
          >
            {evidence.length} 项
          </Badge>
        ) : null}
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2.5 p-2.5">
          {evidence.length === 0 ? (
            <p className="px-3 py-8 text-center text-caption text-muted-foreground">
              回答引用的证据会显示在这里。
            </p>
          ) : (
            evidence.map((item) => <EvidenceCard key={item.chunk_id} item={item} />)
          )}
        </div>
      </ScrollArea>
      <FeedbackBar runtime={runtime} onFeedback={onFeedback} />
    </aside>
  );
}

/** 反馈条：自订阅线程消息取“最近一条完整回答”；选择状态随回答切换自动重置。 */
function FeedbackBar({
  runtime,
  onFeedback,
}: {
  runtime: AssistantRuntime;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
}) {
  const messages = useThreadMessages(runtime);
  const targetId = useMemo(() => latestCompletedAssistantId(messages), [messages]);
  const [selection, setSelection] = useState<{
    id: string;
    value: "like" | "dislike" | null;
  } | null>(null);

  if (!targetId) return null;
  const feedback = selection?.id === targetId ? selection.value : null;

  function toggle(next: "like" | "dislike") {
    const resolved = feedback === next ? null : next;
    setSelection({ id: targetId as string, value: resolved });
    onFeedback(targetId as string, resolved);
  }

  return (
    <div className="border-t border-border/60 bg-panel/20 px-3.5 py-2">
      <div className="flex items-center justify-between">
        <span className="text-metadata text-muted-foreground">这个回答有帮助吗？</span>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="有用"
            aria-pressed={feedback === "like"}
            className={cn(
              "size-7 rounded-lg",
              feedback === "like" && "bg-accent-soft text-accent-soft-ink",
            )}
            onClick={() => toggle("like")}
          >
            <ThumbsUp className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="无用"
            aria-pressed={feedback === "dislike"}
            className={cn(
              "size-7 rounded-lg",
              feedback === "dislike" && "bg-destructive/10 text-destructive",
            )}
            onClick={() => toggle("dislike")}
          >
            <ThumbsDown className="size-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function EvidenceCard({ item }: { item: ChatEvidenceOut }) {
  return (
    <Card className="rounded-xl border border-border/70 bg-surface p-3 transition-all hover:border-border hover:shadow-xs">
      <CardContent className="flex flex-col gap-2 p-0">
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="shrink-0 rounded-md border-accent-ink/25 bg-accent-soft px-1.5 py-0 text-caption font-semibold text-accent-soft-ink"
          >
            {item.citation_label}
          </Badge>
          <span
            className="min-w-0 flex-1 truncate text-caption font-semibold text-ink"
            title={item.title}
          >
            {item.title}
          </span>
          <span className="shrink-0 text-metadata font-mono font-medium text-muted-foreground tabular-nums">
            {Math.round(item.score * 100)}%
          </span>
        </div>
        <div className="flex items-center gap-1 font-mono text-metadata text-muted-foreground">
          <span className="min-w-0 flex-1 truncate">来源 {item.source_id}</span>
          <span className="shrink-0">· 分块 {item.chunk_id}</span>
        </div>
        <p className="rounded-md border-l-2 border-accent-ink/40 bg-panel/30 pl-2 py-1 text-caption leading-relaxed text-body line-clamp-3">
          {item.snippet}
        </p>
      </CardContent>
    </Card>
  );
}
