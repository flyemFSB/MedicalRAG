// 追踪详情（业务运行记录详情 + AI/RAG 阶段时序；Phoenix 仅承载 AI/RAG 观测，fail-open）。
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Activity, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { runQueryOptions } from "../../lib/queries";
import { formatDateTime, formatDuration, runOutcomeLabel, runOutcomeTone } from "../../lib/format";

export const Route = createFileRoute("/admin/traces/$runId")({
  component: TraceDetailScreen,
});

/** 按运行耗时切分的近似阶段时序（后端 run_event 落地后替换为真实数据）。 */
function stageBreakdown(latencyMs: number) {
  const total = Math.max(latencyMs, 1);
  const shares = [0.08, 0.22, 0.3, 0.15, 0.25]; // 改写/意图/检索融合/安全生成前/生成
  const labels = ["问题改写", "意图识别", "检索与融合", "安全校验", "生成回答"];
  let acc = 0;
  return labels.map((label, i) => {
    const duration = Math.round(total * shares[i]);
    const offset = acc;
    acc += duration;
    return { label, duration, offset };
  });
}

export function TraceDetailScreen() {
  const { runId } = Route.useParams();
  const { data: run, isPending } = useQuery(runQueryOptions(runId));

  if (isPending) {
    return (
      <div>
        <div className="skeleton h-40 w-full rounded-lg" />
      </div>
    );
  }
  if (!run) {
    return (
      <div>
        <Card>
          <CardHeader>
            <CardTitle>未找到运行记录</CardTitle>
          </CardHeader>
          <CardContent>缺少该运行记录，可能已被清理。</CardContent>
        </Card>
      </div>
    );
  }

  const stages = stageBreakdown(run.latencyMs);
  const total = Math.max(run.latencyMs, 1);

  return (
    <div>
      <nav aria-label="面包屑" className="mb-3 flex items-center gap-1.5 text-caption text-muted-foreground">
        <Link to="/admin/traces" className="rounded-sm font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">
          链路追踪
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="min-w-0 truncate">{run.runId}</span>
      </nav>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <Activity className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">追踪详情</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">
              运行 {run.runId} · {runOutcomeLabel[run.outcome] ?? run.outcome}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link to="/admin/traces">
            <Button variant="secondary">返回列表</Button>
          </Link>
          {run.traceId ? (
            <Button onClick={() => window.open(`/phoenix/redirects/sessions/${run.traceId}`, "_blank", "noopener")}>
              打开 Phoenix 追踪
            </Button>
          ) : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>运行信息</CardTitle>
          <p className="text-body-sm text-muted-foreground">业务运行记录（PostgreSQL 权威来源）</p>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <DetailItem term="问题" value={run.question} strong />
            <DetailItem
              term="结果"
              value={
                <Badge variant={runOutcomeTone[run.outcome] ?? "neutral"}>
                  {runOutcomeLabel[run.outcome] ?? run.outcome}
                </Badge>
              }
            />
            <DetailItem term="运行 ID" value={run.runId} mono />
            <DetailItem term="会话 ID" value={run.conversationId ?? "—"} mono />
            <DetailItem term="耗时" value={formatDuration(run.latencyMs)} />
            <DetailItem term="执行时间" value={formatDateTime(run.createdAt)} />
            {run.traceId ? <DetailItem term="Trace（观测 Session）" value={run.traceId} mono /> : null}
          </dl>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>AI/RAG 阶段时序</CardTitle>
          <p className="text-body-sm text-muted-foreground">改写 → 意图 → 检索融合 → 安全 → 生成的耗时占比</p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2.5">
            {stages.map((stage) => (
              <div key={stage.label}>
                <div className="flex items-baseline justify-between">
                  <span className="text-body-sm text-ink">{stage.label}</span>
                  <span className="text-caption text-muted-foreground tabular-nums">
                    {formatDuration(stage.duration)} · 起点 {((stage.offset / total) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="relative mt-1 h-1.5 w-full overflow-hidden rounded-full bg-panel">
                  <div
                    className="absolute h-full rounded-full bg-accent-ink"
                    style={{
                      left: `${(stage.offset / total) * 100}%`,
                      width: `${Math.max(1, (stage.duration / total) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-caption text-muted-foreground">
            阶段占比为按耗时估算的近似值；后端 run_event 记录落地后替换为真实阶段数据。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function DetailItem({
  term,
  value,
  mono,
  strong,
}: {
  term: string;
  value: ReactNode;
  mono?: boolean;
  strong?: boolean;
}) {
  return (
    <div className="border-b border-border pb-3">
      <dt className="text-caption text-muted-foreground">{term}</dt>
      <dd
        className={`mt-0.5 text-body-sm ${mono ? "font-mono text-[0.8125rem]" : ""} ${
          strong ? "font-semibold text-ink" : "text-ink"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
