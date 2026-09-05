import { describe, expect, it } from "vitest";
import type { ThreadMessage } from "@assistant-ui/react";
import { pickRecommended, textOf } from "./chat-view";

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

describe("pickRecommended", () => {
  it("returns empty without evidence", () => {
    expect(pickRecommended(0, "answered")).toEqual([]);
  });

  it("returns follow-ups for answered outcomes with evidence", () => {
    expect(pickRecommended(2, "answered")).toHaveLength(2);
  });

  it("suppresses follow-ups for guidance/empty outcomes", () => {
    expect(pickRecommended(2, "guidance")).toEqual([]);
    expect(pickRecommended(2, "empty")).toEqual([]);
    expect(pickRecommended(2, undefined)).toHaveLength(2);
  });
});
