// 审计日志（CONTEXT.md：运营操作变更记录；业务实体的新增/修改/删除/启停）。
import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "../../components/ui/badge";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { AuditEvent } from "../../lib/types";
import { auditQueryOptions } from "../../lib/queries";
import { formatDateTime } from "../../lib/format";

export function AuditScreen() {
  const { data: events = [], isPending } = useQuery(auditQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, AuditEvent>[]>(
    () => [
      { accessorKey: "entityName", header: "实体", cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span> },
      {
        accessorKey: "action",
        header: "操作",
        cell: (info) => {
          const action = info.getValue<string>();
          const variant =
            action === "删除" ? "error" : action === "创建" ? "success" : action === "更新" ? "info" : "warning";
          return <Badge variant={variant}>{action}</Badge>;
        },
      },
      { accessorKey: "entityType", header: "类型", cell: (info) => <Badge variant="neutral">{info.getValue<string>()}</Badge> },
      { accessorKey: "detail", header: "详情", cell: (info) => <span className="text-body">{info.getValue<string>()}</span> },
      { accessorKey: "actorEmail", header: "操作人", cell: (info) => info.getValue<string>() },
      { accessorKey: "createdAt", header: "时间", cell: (info) => <span className="whitespace-nowrap">{formatDateTime(info.getValue<string>())}</span> },
    ],
    [],
  );

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <ScrollText className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">审计日志</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">查看业务数据的新增、修改、删除、启用与禁用记录。</p>
          </div>
        </div>
      </div>
      <div className="mb-3 flex items-center">
        <span className="ml-auto text-caption text-muted-foreground">共 {events.length} 条记录</span>
      </div>
      <DataTable
        ariaLabel="审计日志列表"
        columns={columns}
        data={events}
        loading={isPending}
        emptyTitle="暂无审计记录"
        emptyDescription="运营操作发生后，变更记录会显示在这里。"
      />
    </div>
  );
}
