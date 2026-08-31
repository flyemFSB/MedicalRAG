// 证据面板（右栏：回答引用的证据卡片）。
import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "../ui/scroll-area";
import { cn } from "../../lib/utils";
import type { ChatEvidenceOut } from "../../lib/api";

export function EvidenceList({
  evidence,
  selectedId,
  onSelect,
}: {
  evidence: ChatEvidenceOut[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedId || !panelRef.current) return;
    const card = panelRef.current.querySelector<HTMLElement>(`[data-chunk-id="${selectedId}"]`);
    card?.scrollIntoView({
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }, [selectedId]);

  return (
    <aside aria-label="证据面板" className="hidden min-[1080px]:flex flex-col border-l border-border bg-background">
      <div className="flex items-baseline justify-between px-4 py-3">
        <h2 className="text-caption font-semibold tracking-wide text-muted-foreground uppercase">证据</h2>
        {evidence.length > 0 ? (
          <span className="text-caption text-muted-foreground">{evidence.length} 项</span>
        ) : null}
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div ref={panelRef} className="space-y-2 px-3 pb-4">
          {evidence.length === 0 ? (
            <p className="px-3 py-6 text-center text-body-sm text-muted-foreground">
              回答引用的证据会显示在这里。
            </p>
          ) : (
            evidence.map((item) => (
              <EvidenceCard
                key={item.chunk_id}
                item={item}
                selected={item.chunk_id === selectedId}
                onSelect={onSelect}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}

function EvidenceCard({
  item,
  selected,
  onSelect,
}: {
  item: ChatEvidenceOut;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-chunk-id={item.chunk_id}
      className={cn(
        "rounded-md border border-border bg-background p-3 transition-colors",
        selected ? "border-accent-ink bg-accent-soft" : "border-border",
      )}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onSelect(item.chunk_id)}
          aria-pressed={selected}
          title={item.title}
          className={cn(
            "shrink-0 rounded-md px-2 py-0.5 text-caption font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            selected
              ? "bg-accent-ink text-primary-foreground"
              : "bg-accent-soft text-accent-soft-ink hover:bg-accent-soft/70",
          )}
        >
          {item.citation_label}
        </button>
        <span className="min-w-0 flex-1 truncate text-body-sm font-medium text-ink" title={item.title}>
          {item.title}
        </span>
        <span className="shrink-0 text-caption font-medium text-muted-foreground tabular-nums">
          {(item.score * 100).toFixed(0)}%
        </span>
      </div>
      <div
        className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-panel"
        role="img"
        aria-label={`相关度 ${(item.score * 100).toFixed(0)}%`}
      >
        <div
          className="h-full rounded-full bg-accent-ink"
          style={{ width: `${Math.max(4, Math.round(item.score * 100))}%` }}
        />
      </div>
      <div className="mt-1.5 flex items-center gap-1 font-mono text-caption text-muted-foreground">
        <span className="min-w-0 flex-1 truncate" title={`来源 ${item.source_id}`}>来源 {item.source_id}</span>
        <span className="shrink-0">· 分块 {item.chunk_id}</span>
      </div>
      <p className={cn("mt-1.5 text-body-sm leading-relaxed text-body", !expanded && "line-clamp-2")}>
        {item.snippet}
      </p>
      {item.snippet.length > 90 ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-caption font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {expanded ? "收起" : "展开"}
        </button>
      ) : null}
    </div>
  );
}
