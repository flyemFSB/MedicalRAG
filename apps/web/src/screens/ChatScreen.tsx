// 聊天工作台（证据优先三栏：会话侧栏 + 消息线程/输入 + 证据面板）。
// 本文件只负责「会话状态 + runtime 装配」；展示子模块见 components/chat/。
//
// 聊天运行时：assistant-ui 官方 @assistant-ui/react-langchain useStreamRuntime，
// 包装 @langchain/react v1 useStream + @langchain/langgraph-sdk ThreadStream（transport: sse），
// 直连 Aegra Agent Protocol v2（/api/agent）。无自定义 adapter / SSE 解析。
// 业务键映射：PostgreSQL Conversation.id == Aegra thread_id；分析深度经
// append 的官方 runConfig.custom 桥 → run config.configurable，图侧读取。
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ThreadPrimitive,
  type AssistantRuntime,
} from "@assistant-ui/react";
import { useLangChainState, useStreamRuntime } from "@assistant-ui/react-langchain";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, MessageSquare } from "lucide-react";
import { useEffect, useSyncExternalStore, useState } from "react";
import { Button } from "../components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "../components/ui/sheet";
import { Switch } from "../components/ui/switch";
import { EvidenceList } from "../components/chat/EvidencePanel";
import { MessageRow } from "../components/chat/MessageThread";
import { SessionList, SessionListInner } from "../components/chat/SessionList";
import type { SessionEntry } from "../components/chat/types";
import { WelcomePanel } from "../components/chat/WelcomePanel";
import { createConversation, fetchConversations, submitFeedback, type ChatEvidenceOut } from "../lib/api";

/** 新会话 pending 队列：等 threadId 绑定渲染完成后再经官方 append 桥发送（绕过 React state 异步窗口）。 */
function usePendingAsk(
  runtime: AssistantRuntime,
  pendingQuestion: string | null,
  clearPending: () => void,
  activeId: string | null,
  analysisDepth: boolean,
) {
  useEffect(() => {
    if (pendingQuestion !== null && activeId !== null) {
      clearPending();
  // runConfig.custom → run config.configurable（官方桥），图侧读取 analysis_depth
  void runtime.thread.append({
    role: "user",
    content: [{ type: "text", text: pendingQuestion }],
    runConfig: { custom: { analysis_depth: analysisDepth } },
  });
    }
  }, [pendingQuestion, activeId, analysisDepth, runtime, clearPending]);
}

export function ChatScreen() {
  const { data: backendSessions, refetch } = useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
    staleTime: 30_000,
  });
  const queryClient = useQueryClient();
  const sessions: SessionEntry[] = (backendSessions ?? []).map((c) => ({
    id: c.id,
    title: c.title,
    lastTime: c.updated_at ?? "",
  }));

  const [activeId, setActiveId] = useState<string | null>(null);
  const [analysisDepth, setAnalysisDepth] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  // 官方 v2 运行时：threadId 绑定业务会话（PostgreSQL Conversation.id == Aegra thread_id）。
  // activeId 为 null 时（新会话尚未创建）先经 createConversation 建立业务行再绑定。
  const runtime = useStreamRuntime({
    apiUrl: "/api/agent",
    assistantId: "agent",
    threadId: activeId,
  });

  const ask = async (question: string) => {
    if (activeId === null) {
      // 新会话：先建业务会话行（后端定 id），绑定后发送；避免官方 runtime 自行铸 id 与业务行失配
      const conversation = await createConversation();
      setActiveId(conversation.id);
      setPendingQuestion(question);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      return;
    }
    await runtime.thread.append({
      role: "user",
      content: [{ type: "text", text: question }],
      runConfig: { custom: { analysis_depth: analysisDepth } },
    });
  };

  // 新会话 pending：等 threadId 绑定渲染完成后再 append（官方桥在提交前等待线程初始化）
  usePendingAsk(runtime, pendingQuestion, () => setPendingQuestion(null), activeId, analysisDepth);

  const handleSelectSession = (id: string) => {
    setActiveId(id);
    runtime.thread.reset();
  };

  const handleFeedback = (messageId: string, value: "like" | "dislike" | null) => {
    if (!value) return;
    submitFeedback({
      message_id: messageId,
      conversation_id: activeId ?? "",
      value,
    }).catch(() => {
      // 反馈提交失败不影响对话；可后续补传
    });
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatLayout
        runtime={runtime}
        sessions={sessions}
        activeId={activeId}
        analysisDepth={analysisDepth}
        onNewSession={() => {
          setActiveId(null);
          runtime.thread.reset();
          void refetch();
        }}
        onSelectSession={handleSelectSession}
        onDepthChange={setAnalysisDepth}
        onFeedback={handleFeedback}
        onAsk={ask}
      />
    </AssistantRuntimeProvider>
  );
}

/** 输入区：官方 ComposerPrimitive（IME/焦点/自动高度/发送禁用语义内置）。
 * 提交经官方事件合并机制（composeEventHandlers：我们的 handler 先跑，preventDefault 即跳过内置 send）
 * 拦截到应用层 ask——新会话先建业务行再绑定线程，避免官方 runtime 自行铸 id 与业务会话失配。 */
function ChatComposer({
  runtime,
  onAsk,
  analysisDepth,
  onDepthChange,
}: {
  runtime: AssistantRuntime;
  onAsk: (question: string) => void;
  analysisDepth: boolean;
  onDepthChange: (value: boolean) => void;
}) {
  function submit() {
    const composer = runtime.thread.composer;
    const state = composer.getState();
    const text = state.text.trim();
    if (!text || !state.canSend) return;
    void composer.reset();
    onAsk(text);
  }

  return (
    <ComposerPrimitive.Root
      className="mx-auto max-w-[760px] px-4 py-4 sm:px-6"
      onSubmit={(event) => {
        event.preventDefault(); // 官方合并机制：阻止内置 send，提交走应用层
        submit();
      }}
    >
      <div className="flex items-end gap-2 rounded-lg border border-input bg-surface p-2 pl-4 transition-[border-color,box-shadow] focus-within:border-accent-ink focus-within:ring-2 focus-within:ring-ring">
        <ComposerPrimitive.Input
          placeholder="输入你的问题…"
          aria-label="问题输入框"
          className="max-h-40 min-h-8 flex-1 resize-none bg-transparent text-body text-ink outline-none placeholder:text-muted-foreground"
        />
        <ComposerPrimitive.Send
          aria-label="发送"
          className="inline-flex size-9 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium outline-none transition-[color,background-color,border-color,transform] active:scale-[0.96] disabled:pointer-events-none disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 bg-primary text-primary-foreground hover:bg-primary-hover"
          onClick={(event) => {
            event.preventDefault(); // 官方合并机制：阻止内置 send，提交走应用层
            submit();
          }}
        >
          <ArrowUp />
        </ComposerPrimitive.Send>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-caption text-muted-foreground">
        <span>Enter 发送 · Shift+Enter 换行</span>
        <label className="flex cursor-pointer items-center gap-2">
          <Switch checked={analysisDepth} onCheckedChange={onDepthChange} aria-label="分析深度" />
          分析深度
        </label>
      </div>
    </ComposerPrimitive.Root>
  );
}

function ChatLayout({
  runtime,
  sessions,
  activeId,
  analysisDepth,
  onNewSession,
  onSelectSession,
  onDepthChange,
  onFeedback,
  onAsk,
}: {
  runtime: AssistantRuntime;
  sessions: SessionEntry[];
  activeId: string | null;
  analysisDepth: boolean;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDepthChange: (value: boolean) => void;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
  onAsk: (question: string) => void;
}) {
  const messages = useSyncExternalStore(
    (callback) => runtime.thread.subscribe(callback),
    () => runtime.thread.getState().messages,
  );
  const isEmpty = messages.length === 0;
  // 证据面板 = 当前线程最新一轮证据（Aegra values 通道，官方 useLangChainState）
  const lastEvidence = useLangChainState<ChatEvidenceOut[]>("evidence", []);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);
  const activeTitle = sessions.find((s) => s.id === activeId)?.title;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 text-ink min-[860px]:grid-cols-[220px_minmax(0,1fr)] min-[1080px]:grid-cols-[220px_minmax(0,1fr)_300px]">
      <SessionList sessions={sessions} activeId={activeId} onSelect={onSelectSession} onNew={onNewSession} />

      <section className="flex min-h-0 min-w-0 flex-col bg-background">
        <div className="flex items-center gap-2 border-b border-border bg-background px-3 py-2 min-[860px]:hidden">
          <Sheet open={mobileSessionsOpen} onOpenChange={setMobileSessionsOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-1.5">
                <MessageSquare className="size-4" aria-hidden />
                会话
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="gap-0 bg-panel p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>会话</SheetTitle>
              </SheetHeader>
              <SessionListInner
                sessions={sessions}
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
        <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
          <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-[760px] px-4 py-6 sm:px-6">
              {isEmpty ? (
                <WelcomePanel onAsk={(q) => void onAsk(q)} />
              ) : (
                <>
                  <h1 className="sr-only">对话</h1>
                  <div role="log" aria-live="polite" aria-label="对话记录" className="space-y-6">
                    {messages.map((message) => (
                      <MessageRow
                        key={message.id}
                        message={message}
                        onAsk={(q) => void onAsk(q)}
                        onFeedback={onFeedback}
                        selectedEvidenceId={selectedEvidenceId}
                        onSelectEvidence={setSelectedEvidenceId}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          </ThreadPrimitive.Viewport>

          <div className="border-t border-border bg-canvas/40">
            <ChatComposer runtime={runtime} onAsk={onAsk} analysisDepth={analysisDepth} onDepthChange={onDepthChange} />
          </div>
        </ThreadPrimitive.Root>
      </section>

      <EvidenceList evidence={lastEvidence} selectedId={selectedEvidenceId} onSelect={setSelectedEvidenceId} />
    </div>
  );
}
