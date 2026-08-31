// 链路追踪（CONTEXT.md：Trace 是去标识化的观测记录；业务运行记录存 PostgreSQL，
// 运营从此列表打开 Phoenix 查看 AI/RAG 详情）。
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Activity, ExternalLink, Eye } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { RunRecord } from "../../lib/types";
import { runsQueryOptions } from "../../lib/queries";
import { formatDuration, relativeTime, runOutcomeLabel, runOutcomeTone } from "../../lib/format";

export function TracesScreen() {
  const { data: runs = [], isPending } = useQuery(runsQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, RunRecord>[]>(
    () => [
      { accessorKey: "question", header: "问题", cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span> },
      {
        accessorKey: "outcome",
        header: "结果",
        cell: (info) => (
          <Badge variant={runOutcomeTone[info.getValue<string>()] ?? "neutral"}>
            {runOutcomeLabel[info.getValue<string>()] ?? info.getValue<string>()}
          </Badge>
        ),
      },
      { accessorKey: "modelTarget", header: "模型目标", cell: (info) => info.getValue<string>() ?? <span className="text-muted-foreground">—</span> },
      { accessorKey: "latencyMs", header: "耗时", cell: (info) => formatDuration(info.getValue<number>()) },
      { accessorKey: "createdAt", header: "时间", cell: (info) => relativeTime(info.getValue<string>()) },
    ],
    [],
  );

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <Activity className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">链路追踪</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">业务运行记录存于 PostgreSQL；点击详情可查看阶段，并跳转 Phoenix 查看 AI/RAG 追踪。</p>
          </div>
        </div>
      </div>
      <div className="mb-3 flex items-center">
        <span className="ml-auto text-caption text-muted-foreground">共 {runs.length} 条运行记录</span>
      </div>
      <DataTable
        ariaLabel="运行记录列表"
        columns={columns}
        data={runs}
        loading={isPending}
        emptyTitle="暂无运行记录"
        emptyDescription="用户发起问答后，运行记录会显示在这里。"
        renderRowActions={(run) => (
          <>
            <Button variant="ghost" size="icon" aria-label="查看详情" asChild>
              <Link to="/admin/traces/$runId" params={{ runId: run.id }}>
                <Eye />
              </Link>
            </Button>
            {run.traceId ? (
              <Button
                variant="ghost"
                size="icon"
                aria-label="打开 Phoenix 追踪"
                onClick={() => window.open(`/phoenix/redirects/sessions/${run.traceId}`, "_blank", "noopener")}
              >
                <ExternalLink />
              </Button>
            ) : null}
          </>
        )}
      />
    </div>
  );
}
