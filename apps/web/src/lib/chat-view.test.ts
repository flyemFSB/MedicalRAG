import { describe, expect, it } from "vitest";
import type { ThreadMessage } from "@assistant-ui/react";
import { findLastEvidence, textOf } from "./chat-view";

function assistantMessage(meta?: Record<string, unknown>, text = "回答"): ThreadMessage {
  return {
    id: `msg-${Math.random().toString(36).slice(2)}`,
    role: "assistant",
    content: [{ type: "text", text }],
    status: { type: "complete", reason: "stop" },
    metadata: meta ? { custom: { ...meta } } : undefined,
  } as unknown as ThreadMessage;
}

function userMessage(text: string): ThreadMessage {
  return {
    id: `msg-${Math.random().toString(36).slice(2)}`,
    role: "user",
    content: [{ type: "text", text }],
    status: { type: "complete", reason: "stop" },
    metadata: {},
  } as unknown as ThreadMessage;
}

describe("textOf", () => {
  it("joins text parts of a message", () => {
    expect(textOf(userMessage("hello"))).toBe("hello");
  });
});

describe("findLastEvidence", () => {
  it("returns empty when no assistant message has evidence", () => {
    expect(findLastEvidence([userMessage("q"), assistantMessage(undefined)])).toEqual([]);
  });

  it("returns evidence of the last assistant message that carries it", () => {
    const evidence = [{ chunk_id: "c1", source_id: "s1", title: "t", snippet: "x", citation_label: "[1]", score: 0.9 }];
    const older = assistantMessage({ evidence });
    const newer = assistantMessage({ outcome: "answered" });
    expect(findLastEvidence([older, newer])).toEqual(evidence);
  });

  it("ignores user messages in between", () => {
    const evidence = [{ chunk_id: "c1", source_id: "s1", title: "t", snippet: "x", citation_label: "[1]", score: 0.9 }];
    const withEv = assistantMessage({ evidence });
    const user = userMessage("follow-up");
    const plain = assistantMessage(undefined);
    expect(findLastEvidence([withEv, user, plain])).toEqual(evidence);
  });

  it("returns empty for no messages", () => {
    expect(findLastEvidence([])).toEqual([]);
  });
});
