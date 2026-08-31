// 消息线程（用户/助手消息行 + 反馈 + 安全边界展示）。
import type { ThreadMessage } from "@assistant-ui/react";
import { ShieldAlert, Stethoscope, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";
import type { AssistantMeta } from "../../lib/chat-runtime";
import { textOf } from "../../lib/chat-view";

export function MessageRow({
  message,
  onAsk,
  onFeedback,
  selectedEvidenceId,
  onSelectEvidence,
}: {
  message: ThreadMessage;
  onAsk: (question: string) => void;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
  selectedEvidenceId: string | null;
  onSelectEvidence: (id: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-lg bg-ink px-4 py-3 text-body leading-relaxed whitespace-pre-wrap text-white">
          {textOf(message)}
        </div>
      </div>
    );
  }
  return (
    <AssistantRow
      message={message}
      onAsk={onAsk}
      onFeedback={onFeedback}
      selectedEvidenceId={selectedEvidenceId}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function AssistantRow({
  message,
  onAsk,
  onFeedback,
  selectedEvidenceId,
  onSelectEvidence,
}: {
  message: ThreadMessage;
  onAsk: (question: string) => void;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
  selectedEvidenceId: string | null;
  onSelectEvidence: (id: string) => void;
}) {
  if (message.role !== "assistant") return null;
  const meta = (message.metadata?.custom ?? {}) as Partial<AssistantMeta>;
  const text = textOf(message);
  const isRunning = message.status.type === "running";
  const showError = message.status.type === "incomplete" && !text;

  return (
    <div className="flex gap-3">
      <div
        className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-panel text-muted-foreground"
        aria-hidden
      >
        <Stethoscope className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        {meta.safety?.scope_notice ? (
          <div role="alert" className="mb-4 rounded-md bg-ink p-4">
            <div className="flex items-start gap-3">
              <ShieldAlert className="size-5 shrink-0 self-start text-medical-strong" aria-hidden />
              <div className="min-w-0">
                <p className="text-body-sm font-semibold text-medical-strong">安全边界提醒</p>
                <p className="mt-1 text-body-sm leading-relaxed text-white/90">{meta.safety.scope_notice}</p>
                {meta.safety.escalation ? (
                  <p className="mt-1 text-body-sm leading-relaxed text-white/90">{meta.safety.escalation}</p>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
        {showError ? (
          <Alert variant="error">
            <AlertTitle>回答未生成</AlertTitle>
            <AlertDescription>服务暂时不可用，请稍后再试。你的问题已保留，可直接重新发送。</AlertDescription>
          </Alert>
        ) : (
          <div>
            {text ? (
              <div className="text-body leading-relaxed whitespace-pre-wrap text-ink">
                {text}
                {isRunning ? (
                  <span
                    className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-ink"
                    aria-hidden
                  />
                ) : null}
              </div>
            ) : null}
            {isRunning && !text ? (
              <div className="text-body-sm text-muted-foreground">正在检索证据并生成回答…</div>
            ) : null}
            {!isRunning && meta.evidence && meta.evidence.length > 0 ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                <span className="text-caption font-medium text-muted-foreground">引证</span>
                {meta.evidence.map((e) => {
                  const active = e.chunk_id === selectedEvidenceId;
                  return (
                    <button
                      key={e.chunk_id}
                      type="button"
                      onClick={() => onSelectEvidence(e.chunk_id)}
                      title={e.title}
                      aria-pressed={active}
                      className={cn(
                        "rounded-md px-2 py-0.5 text-caption font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                        active
                          ? "bg-accent-ink text-primary-foreground"
                          : "bg-accent-soft text-accent-soft-ink hover:bg-accent-soft/70",
                      )}
                    >
                      {e.citation_label}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        )}
        {meta.recommended && meta.recommended.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {meta.recommended.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onAsk(q)}
                className="rounded-full border border-border bg-surface px-3 py-1 text-body-sm text-accent-ink outline-none transition-colors hover:border-accent-ink hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-ring"
              >
                {q}
              </button>
            ))}
          </div>
        ) : null}
        {message.status.type === "complete" ? (
          <FeedbackRow messageId={message.id} onFeedback={onFeedback} />
        ) : null}
      </div>
    </div>
  );
}

function FeedbackRow({
  messageId,
  onFeedback,
}: {
  messageId: string;
  onFeedback: (messageId: string, value: "like" | "dislike" | null) => void;
}) {
  const [value, setValue] = useState<"like" | "dislike" | null>(null);

  function toggle(next: "like" | "dislike") {
    const resolved = value === next ? null : next;
    setValue(resolved);
    onFeedback(messageId, resolved);
  }

  return (
    <div className="mt-2 flex gap-1">
      <Button
        variant="ghost"
        size="icon"
        aria-label="有用"
        aria-pressed={value === "like"}
        className={cn("size-7", value === "like" && "bg-accent-soft text-accent-ink hover:bg-accent-soft")}
        onClick={() => toggle("like")}
      >
        <ThumbsUp className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        aria-label="无用"
        aria-pressed={value === "dislike"}
        className={cn("size-7", value === "dislike" && "bg-accent-soft text-accent-ink hover:bg-accent-soft")}
        onClick={() => toggle("dislike")}
      >
        <ThumbsDown className="size-4" />
      </Button>
    </div>
  );
}
