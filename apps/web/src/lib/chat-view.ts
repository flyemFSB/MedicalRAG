// 聊天视图纯函数（消息文本拼接 / 推荐追问计算）。
import type { ThreadMessage } from "@assistant-ui/react";
import type { ChatEvidenceOut } from "./api";

/** 助手消息元数据：图经 AIMessage.additional_kwargs["custom"] 写出，assistant-ui 官方桥透传为消息 metadata.custom。 */
export type AssistantMeta = {
  evidence?: ChatEvidenceOut[];
  safety?: { risk_class?: string; scope_notice?: string | null; escalation?: string | null };
  outcome?: string;
} & Record<string, unknown>;

export function textOf(message: ThreadMessage): string {
  return message.content
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

export function pickRecommended(evidenceCount: number, outcome: string | undefined): string[] {
  if (!evidenceCount) return [];
  return outcome === "guidance" || outcome === "empty" ? [] : ["这些来源的结论依据是什么？", "证据中提到的数值有更新吗？"];
}
