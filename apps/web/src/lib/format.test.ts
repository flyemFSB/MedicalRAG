// 展示格式化纯函数单元测试（ADR 0080：web 补齐 test:unit 层）。
import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration, ingestionStatusLabel, relativeTime } from "./format";

describe("relativeTime", () => {
  it("空值与非法值返回占位符", () => {
    expect(relativeTime(undefined)).toBe("—");
    expect(relativeTime("not-a-date")).toBe("—");
  });

  it("刚刚 / 分钟前", () => {
    const now = Date.now();
    expect(relativeTime(new Date(now - 10_000).toISOString())).toBe("刚刚");
    expect(relativeTime(new Date(now - 5 * 60_000).toISOString())).toBe("5 分钟前");
  });

  it("小时前 / 天前", () => {
    const now = Date.now();
    expect(relativeTime(new Date(now - 3 * 3_600_000).toISOString())).toBe("3 小时前");
    expect(relativeTime(new Date(now - 2 * 86_400_000).toISOString())).toBe("2 天前");
  });
});

describe("formatBytes / formatDuration", () => {
  it("字节与 KB/MB 边界", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(1024 ** 2)).toBe("1.0 MB");
  });

  it("毫秒与秒边界", () => {
    expect(formatDuration(250)).toBe("250 ms");
    expect(formatDuration(1500)).toBe("1.5 s");
  });
});

describe("摄取状态词表一致性", () => {
  it("每个摄取状态都有中文文案", () => {
    for (const tone of Object.values(ingestionStatusLabel)) {
      // 摄取状态文案必须非空
      expect(tone.length).toBeGreaterThan(0);
    }
  });
});
