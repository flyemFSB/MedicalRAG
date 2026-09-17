// 模型目标状态 → 语义状态（供状态徽章配色）。
import type { SemStatus } from "./types";

export const modelTargetTone: Record<string, SemStatus> = {
  healthy: "success",
  degraded: "warning",
  unreachable: "error",
};

// 语义状态 → 结构 Badge 变体 + 语义配色工具类。
// shadcn base-ui 徽章只有结构变体（default/secondary/destructive/outline...），
// 语义色经库组件自身的工具类合成，不改动库组件本体。
export function badgeSem(status: SemStatus): {
  variant: "default" | "secondary" | "destructive" | "outline";
  className?: string;
} {
  switch (status) {
    case "success":
      return { variant: "outline", className: "border-success/40 text-success" };
    case "warning":
      return { variant: "outline", className: "border-warning/40 text-warning" };
    case "error":
      return { variant: "destructive" };
    case "info":
      return { variant: "outline", className: "border-info/40 text-info" };
    default:
      return { variant: "secondary" };
  }
}
