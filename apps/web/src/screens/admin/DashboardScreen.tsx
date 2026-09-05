// 仪表盘（recharts KPI 与趋势；DESIGN §5.4 工作面板而非 hero）。
import { useSuspenseQuery } from "@tanstack/react-query";
import { BookOpen, Cpu, LayoutDashboard, TriangleAlert, type LucideIcon } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { dashboardQueryOptions } from "../../lib/queries";
import { formatDuration, relativeTime } from "../../lib/format";
import { modelTargetTone } from "../../lib/status";

/** 从 tokens.css 读取设计 token（DESIGN 禁止 ad-hoc 色）。 */
function tokenColor(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function DashboardScreen() {
  const { data } = useSuspenseQuery(dashboardQueryOptions());
  const targetCount = data.activeModelTargets + data.degradedModelTargets;
  const accent = tokenColor("--color-accent-ink");
  const success = tokenColor("--color-success");
  const grid = tokenColor("--color-border");
  const axis = tokenColor("--color-muted");

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <LayoutDashboard className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">仪表盘</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">摄取、聊天、模型与检索指标的运行概览。</p>
          </div>
        </div>
      </div>

      <div className="mb-6 grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="会话数" value={data.totalChats} />
        <StatCard label="提问数" value={data.totalQuestions} />
        <StatCard label="平均响应" value={formatDuration(data.avgLatencyMs)} />
        <StatCard label="已发布文档" value={data.publishedDocs} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>提问趋势</CardTitle>
            <p className="text-body-sm text-muted-foreground">最近 7 天每日提问数</p>
          </CardHeader>
          <CardContent>
            {data.questionTrend.length === 0 ? (
              <ChartPlaceholder />
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={data.questionTrend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="questionFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={accent} stopOpacity={0.18} />
                      <stop offset="100%" stopColor={accent} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: axis }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: axis }} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: `1px solid ${grid}`, boxShadow: "0 4px 8px rgb(0 0 0 / 0.06)", fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="value" name="提问数" stroke={accent} strokeWidth={2} fill="url(#questionFill)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>摄取完成数</CardTitle>
            <p className="text-body-sm text-muted-foreground">最近 7 天已发布文档数</p>
          </CardHeader>
          <CardContent>
            {data.ingestionTrend.length === 0 ? (
              <ChartPlaceholder />
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={data.ingestionTrend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: axis }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: axis }} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: `1px solid ${grid}`, boxShadow: "0 4px 8px rgb(0 0 0 / 0.06)", fontSize: 12 }}
                  />
                  <Bar dataKey="value" name="已发布" fill={success} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>模型目标健康</CardTitle>
            <p className="text-body-sm text-muted-foreground">生成/嵌入/重排目标的熔断状态</p>
          </CardHeader>
          <CardContent>
            <Table aria-label="模型目标健康">
              <TableHeader>
                <TableRow>
                  <TableHead>目标</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>熔断</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.modelTargets.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-medium text-ink">{t.name}</TableCell>
                    <TableCell>{t.provider}</TableCell>
                    <TableCell>
                      <Badge variant={modelTargetTone[t.status]}>
                        {t.status === "healthy" ? "健康" : t.status === "degraded" ? "降级" : "不可达"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[0.8125rem]">
                      {t.circuitState === "closed" ? "关闭" : t.circuitState === "open" ? "熔断" : "半开"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>近期运行</CardTitle>
            <p className="text-body-sm text-muted-foreground">最近的回答运行</p>
          </CardHeader>
          <CardContent>
            <Table aria-label="近期运行">
              <TableHeader>
                <TableRow>
                  <TableHead>问题</TableHead>
                  <TableHead>结果</TableHead>
                  <TableHead className="text-right">耗时</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recentRuns.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium text-ink">{r.question}</TableCell>
                    <TableCell>
                      <Badge variant={r.outcome === "completed" ? "success" : r.outcome === "failed" ? "error" : "warning"}>
                        {r.outcome}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatDuration(r.latencyMs)}</TableCell>
                    <TableCell>{relativeTime(r.createdAt)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
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
    <div className="flex items-center gap-3 rounded-md border border-border bg-surface px-4 py-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-panel text-muted-foreground">
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-caption text-muted-foreground">{label}</p>
        <p className="text-body-sm font-semibold text-ink">
          {value}
          {hint ? (
            <span className={`ml-1.5 text-caption font-normal ${STAT_TONE_TEXT[tone ?? ""] ?? "text-muted-foreground"}`}>
              {hint}
            </span>
          ) : null}
        </p>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
  hintTone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  hintTone?: "success" | "warning";
}) {
  return (
    <div className="bg-background px-5 py-5">
      <p className="text-caption font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-display font-semibold tabular-nums text-ink">{value}</p>
      {hint ? (
        <p className={`mt-1 text-caption ${hintTone === "success" ? "text-success" : hintTone === "warning" ? "text-warning" : "text-muted-foreground"}`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function ChartPlaceholder() {
  return (
    <div className="grid h-60 place-items-center rounded-md border border-dashed border-border text-body-sm text-muted-foreground">
      趋势数据接入后显示在这里
    </div>
  );
}
