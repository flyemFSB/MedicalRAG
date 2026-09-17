// 服务状态页：Router loader 预热 → useSuspenseQuery → 按健康/降级分组的检查清单。
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Badge } from "../components/ui/badge";
import { healthQueryOptions } from "../lib/queries";
import { badgeSem } from "../lib/status";
import { cn } from "../lib/utils";

export const Route = createFileRoute("/status")({
  loader: ({ context }) => context.queryClient.ensureQueryData(healthQueryOptions()),
  component: StatusScreen,
});

function isHealthy(status: string): boolean {
  return status === "healthy" || status === "ok";
}

function StatusScreen() {
  const { data } = useSuspenseQuery(healthQueryOptions());
  const checks = Object.entries(data.checks);
  const healthy = checks.filter(([, status]) => isHealthy(status));
  const degraded = checks.filter(([, status]) => !isHealthy(status));

  return (
    <div className="mx-auto w-full max-w-3xl overflow-y-auto p-2 sm:p-4">
      <div className="rounded-2xl border border-border/80 bg-surface p-6 shadow-[var(--shadow-island)] sm:p-8">
        <div className="mb-6 flex items-center justify-between border-b border-border/40 pb-5">
          <div className="flex items-center gap-3">
            <h1 className="text-heading-lg font-semibold tracking-tight text-ink">服务状态</h1>
            <Badge {...badgeSem(data.status === "healthy" ? "success" : "warning")}>
              {data.status === "healthy" ? "健康" : "降级"}
            </Badge>
          </div>
          <span className="font-mono text-metadata text-muted-foreground">实时运行监测</span>
        </div>
        {degraded.length > 0 ? (
          <section aria-label="降级服务" className="mb-6">
            <h2 className="mb-2.5 font-mono text-metadata font-semibold tracking-wider text-muted-foreground uppercase">
              降级
            </h2>
            <div className="space-y-2">
              {degraded.map(([name, status]) => (
                <CheckRow key={name} name={name} status={status} />
              ))}
            </div>
          </section>
        ) : null}
        <section aria-label="健康服务">
          <h2 className="mb-2.5 font-mono text-metadata font-semibold tracking-wider text-muted-foreground uppercase">
            健康
          </h2>
          {healthy.length === 0 ? (
            <p className="rounded-xl border border-border/70 bg-panel/40 px-4 py-6 text-center text-body-sm text-muted-foreground">
              暂无健康检查项。
            </p>
          ) : (
            <div className="space-y-2">
              {healthy.map(([name, status]) => (
                <CheckRow key={name} name={name} status={status} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function CheckRow({ name, status }: { name: string; status: string }) {
  const healthy = isHealthy(status);
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-surface px-4 py-3 shadow-2xs transition-colors hover:bg-panel/40">
      <div className="flex min-w-0 items-center gap-2.5">
        <span
          className={cn("size-2 shrink-0 rounded-full", healthy ? "bg-success" : "bg-warning")}
          aria-hidden
        />
        <span className="truncate text-body-sm font-medium text-ink">{name}</span>
      </div>
      <Badge {...badgeSem(healthy ? "success" : "warning")}>{healthy ? "健康" : "降级"}</Badge>
    </div>
  );
}
