// 模型目标状态 → 语义状态（供状态徽章配色）。
import type { SemStatus } from "./types";

export const modelTargetTone: Record<string, SemStatus> = {
  healthy: "success",
  degraded: "warning",
  unreachable: "error",
};
