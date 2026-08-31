// 聊天工作台（证据优先三栏：会话侧栏 + 消息线程/输入 + 证据面板）。
// 本文件只负责「会话状态 + runtime 装配」；展示子模块见 components/chat/。
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type AssistantRuntime,
} from "@assistant-ui/react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, MessageSquare } from "lucide-react";
import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Button } from "../components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "../components/ui/sheet";
import { Switch } from "../components/ui/switch";
import { EvidenceList } from "../components/chat/EvidencePanel";
import { MessageRow } from "../components/chat/MessageThread";
import { SessionList, SessionListInner } from "../components/chat/SessionList";
import type { SessionEntry } from "../components/chat/types";
import { WelcomePanel } from "../components/chat/WelcomePanel";
import { fetchConversations, submitFeedback } from "../lib/api";
import { createChatAdapter } from "../lib/chat-runtime";
import { findLastEvidence } from "../lib/chat-view";

export function ChatScreen() {
  const { data: backendSessions } = useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
    staleTime: 30_000,
  });
  const sessions: SessionEntry[] = (backendSessions ?? []).map((c) => ({
    id: c.id,
    title: c.title,
    lastTime: c.updated_at ?? "",
  }));

  const [activeId, setActiveId] = useState<string | null>(null);
  const [analysisDepth, setAnalysisDepth] = useState(false);
  const conversationIdRef = useRef<string>(`local-${Date.now().toString(36)}`);
  const analysisDepthRef = useRef(false);
  const refsRef = useRef({
    conversationId: () => conversationIdRef.current,
    analysisDepth: () => analysisDepthRef.current,
  });

  // adapter 用 useMemo([]) 保持稳定；运行期可变状态走 refs，避免重建 runtime。
  const adapter = useMemo(() => createChatAdapter(refsRef.current), []);
  const runtime = useLocalRuntime(adapter);

  function handleNewSession() {
    setActiveId(null);
    conversationIdRef.current = `local-${Date.now().toString(36)}`;
    runtime.thread.reset();
  }

  function handleSelectSession(id: string) {
    setActiveId(id);
    conversationIdRef.current = id;
    runtime.thread.reset();
  }

  function handleDepthChange(value: boolean) {
    setAnalysisDepth(value);
    analysisDepthRef.current = value;
  }

  function handleFeedback(messageId: string, value: "like" | "dislike" | null) {
    if (!value) return;
    submitFeedback({
      message_id: messageId,
      conversation_id: conversationIdRef.current,
      value,
    }).catch(() => {
      // 反馈提交失败不影响对话；可后续补传
    });
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatLayout
        runtime={runtime}
        sessions={sessions}
        activeId={activeId}
        analysisDepth={analysisDepth}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onDepthChange={handleDepthChange}
        onFeedback={handleFeedback}
      />
    </AssistantRuntimeProvider>
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
}: {
  runtime: AssistantRuntime;
  sessions: SessionEntry[];
  activeId: string | null;
  analysisDepth: boolean;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDepthChange: (value: boolean) => void;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
}) {
  const messages = useSyncExternalStore(
    (callback) => runtime.thread.subscribe(callback),
    () => runtime.thread.getState().messages,
  );
  const isEmpty = messages.length === 0;
  const lastEvidence = useMemo(() => findLastEvidence(messages), [messages]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);
  const activeTitle = sessions.find((s) => s.id === activeId)?.title;
  const ask = (question: string) => runtime.thread.append(question);

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
                <WelcomePanel onAsk={ask} />
              ) : (
                <>
                  <h1 className="sr-only">对话</h1>
                  <div role="log" aria-live="polite" aria-label="对话记录" className="space-y-6">
                    {messages.map((message) => (
                      <MessageRow
                        key={message.id}
                        message={message}
                        onAsk={ask}
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
            <ComposerPrimitive.Root className="mx-auto max-w-[760px] px-4 py-4 sm:px-6">
              <div className="flex items-end gap-2 rounded-lg border border-input bg-surface p-2 pl-4 transition-[border-color,box-shadow] focus-within:border-accent-ink focus-within:ring-2 focus-within:ring-ring">
                <ComposerPrimitive.Input
                  placeholder="输入你的问题…"
                  aria-label="问题输入框"
                  className="max-h-40 flex-1 resize-none bg-transparent text-body text-ink outline-none placeholder:text-muted-foreground"
                />
                <ComposerPrimitive.Send asChild>
                  <Button size="icon" aria-label="发送" className="size-9 shrink-0 rounded-md">
                    <ArrowUp />
                  </Button>
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
          </div>
        </ThreadPrimitive.Root>
      </section>

      <EvidenceList evidence={lastEvidence} selectedId={selectedEvidenceId} onSelect={setSelectedEvidenceId} />
    </div>
  );
}
