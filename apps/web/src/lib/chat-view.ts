// 聊天视图纯函数（从 ChatScreen 抽出：消息文本拼接 / 最新证据查找）。
import type { ThreadMessage } from "@assistant-ui/react";
import type { ChatEvidenceOut } from "./api";
import type { AssistantMeta } from "./chat-runtime";

export function textOf(message: ThreadMessage): string {
  return message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

export function findLastEvidence(messages: readonly ThreadMessage[]): ChatEvidenceOut[] {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role !== "assistant") continue;
    const meta = (message.metadata?.custom ?? {}) as Partial<AssistantMeta>;
    if (meta.evidence && meta.evidence.length > 0) return meta.evidence;
  }
  return [];
}
