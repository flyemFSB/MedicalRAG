// 追踪详情（业务运行记录详情；Phoenix 仅承载 AI/RAG 观测，fail-open）。
// 注：AI/RAG 阶段时序卡已删除——按总耗时硬编码占比反推的“阶段数据”是编造的观测数据，
// 违背证据优先的可信度红线；待后端 run_event 真实阶段记录落地后再回加（判例同 DashboardScreen）。
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Activity, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { badgeSem } from "../../lib/status";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { runQueryOptions } from "../../lib/queries";
import { formatDateTime, formatDuration, runOutcomeLabel, runOutcomeTone } from "../../lib/format";

const Route = createFileRoute("/admin/traces/$runId")({});

export function TraceDetailScreen() {
  const { runId } = Route.useParams();
  const { data: run, isPending } = useQuery(runQueryOptions(runId));

  if (isPending) {
    return (
      <div>
        <Skeleton className="h-40 w-full rounded-lg" />
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

  return (
    <div>
      <nav
        aria-label="面包屑"
        className="mb-3 flex items-center gap-1.5 text-caption text-muted-foreground"
      >
        <Link
          to="/admin/traces"
          className="rounded-sm font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          链路追踪
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="min-w-0 truncate">{run.runId}</span>
      </nav>
      <AdminPageHeader
        icon={Activity}
        title="追踪详情"
        description={`运行 ${run.runId} · ${runOutcomeLabel[run.outcome] ?? run.outcome}`}
        actions={
          <>
            <Link to="/admin/traces">
              <Button variant="secondary">返回列表</Button>
            </Link>
            {run.traceId ? (
              <Button
                onClick={() =>
                  window.open(`/phoenix/redirects/sessions/${run.traceId}`, "_blank", "noopener")
                }
              >
                打开 Phoenix 追踪
              </Button>
            ) : null}
          </>
        }
      />

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
                <Badge {...badgeSem(runOutcomeTone[run.outcome] ?? "neutral")}>
                  {runOutcomeLabel[run.outcome] ?? run.outcome}
                </Badge>
              }
            />
            <DetailItem term="运行 ID" value={run.runId} mono />
            <DetailItem term="会话 ID" value={run.conversationId ?? "—"} mono />
            <DetailItem term="耗时" value={formatDuration(run.latencyMs)} />
            <DetailItem term="执行时间" value={formatDateTime(run.createdAt)} />
            {run.traceId ? (
              <DetailItem term="Trace（观测 Session）" value={run.traceId} mono />
            ) : null}
          </dl>
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
