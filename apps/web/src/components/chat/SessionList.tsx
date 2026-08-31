// 会话侧栏（聊天工作台左栏：新建/选择会话）。
import { MessageSquare, Plus } from "lucide-react";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";
import { relativeTime } from "../../lib/format";
import type { SessionEntry } from "./types";

export function SessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: SessionEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <nav
      aria-label="会话列表"
      className="hidden w-[220px] flex-col border-r border-border bg-background min-[860px]:flex"
    >
      <SessionListInner sessions={sessions} activeId={activeId} onSelect={onSelect} onNew={onNew} />
    </nav>
  );
}

export function SessionListInner({
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: SessionEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <>
      <div className="flex items-center justify-between px-3 py-3">
        <h2 className="text-caption font-semibold tracking-wide text-muted-foreground uppercase">会话</h2>
        <Button variant="ghost" size="sm" className="gap-1" onClick={onNew}>
          <Plus className="size-4" aria-hidden />
          新建
        </Button>
      </div>
      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {sessions.length === 0 ? (
          <p className="px-3 py-2 text-body-sm text-muted-foreground">还没有会话</p>
        ) : (
          sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => onSelect(session.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-body-sm text-body outline-none transition-colors hover:bg-panel/60 hover:text-ink focus-visible:ring-2 focus-visible:ring-ring",
                session.id === activeId &&
                  "bg-panel font-medium text-ink hover:bg-panel hover:text-ink",
              )}
            >
              <MessageSquare className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{session.title}</span>
              <span className="shrink-0 text-caption text-muted-foreground">
                {relativeTime(session.lastTime)}
              </span>
            </button>
          ))
        )}
      </div>
    </>
  );
}
