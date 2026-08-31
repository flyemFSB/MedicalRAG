// 展示格式化工具（中文 UI 文案；时间用相对时间，遵循 DESIGN 状态性而非装饰）。
import type { SemStatus } from "./types";

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期。 */
export function relativeTime(iso: string | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = now - then;
  if (Number.isNaN(then)) return "—";
  const minute = 60_000;
  const hour = 3_600_000;
  const day = 86_400_000;
  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

/** 完整日期时间（表格列用）。 */
export function formatDateTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

/** 字节数 → 人类可读（KB/MB）。 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

/** 毫秒 → 秒（保留一位）。 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** 摄取状态 → 语义状态（供状态徽章配色）。 */
export const ingestionStatusTone: Record<string, SemStatus> = {
  published: "success",
  validating: "info",
  indexing: "info",
  embedding: "info",
  chunking: "info",
  extracting: "info",
  accepted: "neutral",
  failed: "error",
};

/** 摄取状态 → 中文文案。 */
export const ingestionStatusLabel: Record<string, string> = {
  accepted: "已受理",
  extracting: "解析抽取",
  chunking: "结构分块",
  embedding: "向量嵌入",
  indexing: "索引入库",
  validating: "校验复核",
  published: "已发布",
  failed: "失败",
};

/** 运行结果 → 语义状态。 */
export const runOutcomeTone: Record<string, SemStatus> = {
  completed: "success",
  guidance: "warning",
  empty: "warning",
  fallback: "warning",
  cancelled: "neutral",
  failed: "error",
};

/** 运行结果 → 中文文案。 */
export const runOutcomeLabel: Record<string, string> = {
  completed: "已回答",
  guidance: "澄清引导",
  empty: "无证据",
  fallback: "降级回答",
  cancelled: "已取消",
  failed: "失败",
};

/** 文档格式中文名。 */
export const formatLabel: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  pptx: "PPT",
  xlsx: "Excel",
  md: "Markdown",
  txt: "纯文本",
  png: "图片",
  jpg: "图片",
  jpeg: "图片",
};
