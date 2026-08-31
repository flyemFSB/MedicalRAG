// 聊天运行时（assistant-ui 自定义 ChatModelAdapter：把 /api/chat/stream 的 SSE
// 事件流映射为消息 part 与 metadata.custom——证据/安全/结果存于消息元数据，随消息持久）。
import type {
  ChatModelAdapter,
  ChatModelRunResult,
  ThreadAssistantMessagePart,
} from "@assistant-ui/react";
import type { ChatEvidenceOut } from "./api";
import { textOf } from "./chat-view";

/** 助手消息元数据（写进 metadata.custom，随消息携带/持久）。 */
export type AssistantMeta = {
  evidence?: ChatEvidenceOut[];
  safety?: {
    risk_class?: string;
    scope_notice?: string | null;
    escalation?: string | null;
  };
  outcome?: string;
  recommended?: string[];
} & Record<string, unknown>;

/** adapter 运行期读取的外部可变状态（refs，避免 adapter 重建）。 */
export interface ChatRunRefs {
  conversationId: () => string;
  analysisDepth: () => boolean;
}

function pickRecommended(evidenceCount: number, outcome: string): string[] {
  if (evidenceCount === 0) return [];
  return outcome === "guidance" || outcome === "empty"
    ? []
    : ["这些来源的结论依据是什么？", "证据中提到的数值有更新吗？"];
}

export function createChatAdapter(refs: ChatRunRefs): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      const question = lastUser ? textOf(lastUser) : "";

      const response = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          conversation_id: refs.conversationId(),
          analysis_depth: refs.analysisDepth(),
        }),
        signal: abortSignal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`聊天服务不可用（HTTP ${response.status}）`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let text = "";
      let custom: AssistantMeta = {};

      const emit = (
        patch: { text?: string; custom?: Partial<AssistantMeta> },
      ): ChatModelRunResult => {
        if (patch.text !== undefined) text = patch.text;
        if (patch.custom !== undefined) custom = { ...custom, ...patch.custom };
        return {
          ...(patch.text !== undefined
            ? { content: [{ type: "text", text }] satisfies ThreadAssistantMessagePart[] }
            : {}),
          ...(patch.custom !== undefined ? { metadata: { custom } } : {}),
        };
      };

      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          for (const block of buffer.split("\n\n")) {
            if (!block.includes("data:")) continue;
            const eventLine = block.split("\n").find((l) => l.startsWith("event:"));
            const dataLine = block.split("\n").find((l) => l.startsWith("data:"));
            if (!eventLine || !dataLine) continue;
            const event = eventLine.slice(5).trim();
            const data = JSON.parse(dataLine.slice(5).trim());
            if (event === "token") {
              yield emit({ text: text + data.text });
            } else if (event === "evidence") {
              yield emit({ custom: { evidence: data.evidence } });
            } else if (event === "safety") {
              yield emit({
                custom: {
                  safety: {
                    risk_class: data.risk_class,
                    scope_notice: data.scope_notice ?? null,
                    escalation: data.escalation ?? null,
                  },
                },
              });
            } else if (event === "done") {
              yield emit({
                text: data.message,
                custom: {
                  evidence: data.evidence,
                  outcome: data.outcome,
                  safety: data.safety_notice
                    ? {
                        risk_class: data.risk_class ?? "",
                        scope_notice: data.safety_notice,
                        escalation: data.safety_escalation ?? null,
                      }
                    : undefined,
                  recommended: pickRecommended(data.evidence.length, data.outcome),
                },
              });
            }
          }
          buffer = buffer.split("\n\n").pop() ?? "";
        }
        // 流正常结束但既无正文也无证据 → 视为失败，让 runtime 标记错误态。
        if (!text && !custom.evidence) {
          throw new Error("流式响应结束但未收到完整回答");
        }
      } finally {
        try {
          reader.releaseLock();
        } catch {
          // 忽略释放异常（流已被中断时）
        }
      }
    },
  };
}
