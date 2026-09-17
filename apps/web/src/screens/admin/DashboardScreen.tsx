// 仪表盘（KPI 概览；DESIGN §5.4 工作面板而非 hero）。
// 趋势图表 / 模型目标明细 / 近期运行等恒空区块已删（API 未提供，见 complexity-audit P1）。
import { useSuspenseQuery } from "@tanstack/react-query";
import { BookOpen, Cpu, LayoutDashboard, TriangleAlert, type LucideIcon } from "lucide-react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { dashboardQueryOptions } from "../../lib/queries";
import { formatDuration } from "../../lib/format";

export function DashboardScreen() {
  const { data } = useSuspenseQuery(dashboardQueryOptions());
  const targetCount = data.activeModelTargets + data.degradedModelTargets;

  return (
    <div>
      <AdminPageHeader
        icon={LayoutDashboard}
        title="仪表盘"
        description="摄取、聊天、模型与检索指标的运行概览。"
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="会话数" value={data.totalChats} />
        <StatCard label="提问数" value={data.totalQuestions} />
        <StatCard label="平均响应" value={formatDuration(data.avgLatencyMs)} />
        <StatCard label="已发布文档" value={data.publishedDocs} />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryStat icon={BookOpen} label="已发布文档" value={`${data.publishedDocs} 篇`} />
        <SummaryStat
          icon={TriangleAlert}
          label="失败运行"
          value={`${data.failedRuns} 次`}
          tone={data.failedRuns > 0 ? "error" : "success"}
        />
        <SummaryStat
          icon={Cpu}
          label="模型目标"
          value={`${targetCount} 个`}
          hint={data.degradedModelTargets > 0 ? `${data.degradedModelTargets} 个降级` : "全部健康"}
          tone={data.degradedModelTargets > 0 ? "warning" : "success"}
        />
      </div>
    </div>
  );
}

const STAT_TONE_TEXT: Record<string, string> = {
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
};

function SummaryStat({
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  tone?: "success" | "warning" | "error";
}) {
  return (
    <div className="flex items-center gap-3.5 rounded-xl border border-border/80 bg-surface p-4 shadow-2xs transition-all hover:border-border hover:shadow-xs">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-panel/70 text-muted-foreground ring-1 ring-border/50">
        <Icon className="size-4 text-ink/80" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-caption text-muted-foreground">{label}</p>
        <p className="text-body-sm font-semibold text-ink">
          {value}
          {hint ? (
            <span
              className={`ml-1.5 text-caption font-normal ${STAT_TONE_TEXT[tone ?? ""] ?? "text-muted-foreground"}`}
            >
              {hint}
            </span>
          ) : null}
        </p>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border/80 bg-surface p-4 sm:p-5 shadow-2xs transition-all hover:border-border hover:shadow-xs">
      <p className="text-caption font-medium text-muted-foreground">{label}</p>
      <p className="mt-2 font-display text-display font-semibold tabular-nums text-ink leading-none">
        {value}
      </p>
    </div>
  );
}
