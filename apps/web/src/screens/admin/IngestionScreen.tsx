// 摄取运行（CONTEXT.md：把文档转成验证过的分块与已发布版本的异步可观测执行；
// 九阶段状态机 + 失败阶段修复）。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { badgeSem } from "../../lib/status";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { cn } from "../../lib/utils";
import { adminKeys, ingestionRunsQueryOptions } from "../../lib/queries";
import { retryIngestionRun } from "../../lib/api";
import { formatDateTime, ingestionStatusLabel, ingestionStatusTone } from "../../lib/format";

const STAGE_DOT: Record<string, string> = {
  running: "●",
  succeeded: "✓",
  failed: "✕",
};

function StagePill({ status, label }: { status: string; label: string }) {
  return (
    <li
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption",
        status === "succeeded" && "bg-success-soft text-success",
        status === "running" && "bg-info-soft text-info",
        status === "failed" && "bg-error-soft text-error",
        status === "pending" && "bg-panel text-muted-foreground",
      )}
    >
      {STAGE_DOT[status] ?? "·"}
      {label}
    </li>
  );
}

export function IngestionScreen() {
  const queryClient = useQueryClient();
  // 加载/错误/空三态齐全：请求失败不能渲染成“暂无运行”假空态
  const { data: runs = [], isPending, isError, refetch } = useQuery(ingestionRunsQueryOptions());

  const retryMutation = useMutation({
    mutationFn: retryIngestionRun,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.ingestion });
      toast.success("已重试该阶段");
    },
    onError: () => toast.error("重试失败"),
  });

  return (
    <div>
      <AdminPageHeader
        icon={Upload}
        title="摄取运行"
        description="监控文档摄取的执行状态，在失败阶段定点重试。"
      />
      <div className="grid gap-4">
        {isPending ? (
          Array.from({ length: 2 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))
        ) : isError ? (
          <Card>
            <CardContent className="py-5 text-body-sm text-destructive" role="alert">
              摄取运行加载失败，
              <button
                type="button"
                className="font-medium text-accent-ink underline outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => refetch()}
              >
                点击重试
              </button>
            </CardContent>
          </Card>
        ) : runs.length === 0 ? (
          <Card>
            <CardContent className="py-5 text-body-sm text-muted-foreground">
              还没有摄取运行；上传文档后将在此展示执行进度。
            </CardContent>
          </Card>
        ) : (
          runs.map((run) => {
            const failed = run.status === "failed";
            return (
              <Card key={run.id}>
                <CardContent className="py-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-ink">{run.documentTitle}</div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge {...badgeSem(ingestionStatusTone[run.status] ?? "neutral")}>
                        {ingestionStatusLabel[run.status] ?? run.status}
                      </Badge>
                      {failed ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => retryMutation.mutate(run.id)}
                          disabled={retryMutation.isPending}
                        >
                          重试
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <ul aria-label="摄取阶段" className="mt-3 flex flex-wrap items-center gap-1.5">
                    {run.stages.map((stage) => (
                      <StagePill key={stage.name} status={stage.status} label={stage.label} />
                    ))}
                  </ul>
                  <p className="mt-3 text-caption text-muted-foreground">
                    开始于 {formatDateTime(run.startedAt)}
                  </p>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
