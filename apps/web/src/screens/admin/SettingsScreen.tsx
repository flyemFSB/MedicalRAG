// 模型设置（CONTEXT.md：模型目标 = 配置的模型提供方与能力集）。
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Settings2 } from "lucide-react";
import { useMemo } from "react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { DataTable } from "../../components/data-table";
import type { AppTableFeatures } from "../../lib/table";
import { modelTargetStatusLabel, circuitStateLabel } from "../../lib/format";
import { badgeSem, modelTargetTone } from "../../lib/status";
import type { ModelTarget } from "../../lib/types";
import { modelTargetsQueryOptions } from "../../lib/queries";

export function SettingsScreen() {
  const { data: targets = [], isError, isPending, refetch } = useQuery(modelTargetsQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, ModelTarget>[]>(
    () => [
      {
        accessorKey: "name",
        header: "目标",
        cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span>,
      },
      {
        accessorKey: "provider",
        header: "类型",
        cell: (info) => <Badge {...badgeSem("neutral")}>{info.getValue<string>()}</Badge>,
      },
      {
        accessorKey: "model",
        header: "模型",
        cell: (info) => (
          <span className="font-mono text-[0.8125rem]">{info.getValue<string>()}</span>
        ),
      },
      {
        accessorKey: "capabilities",
        header: "能力",
        cell: (info) => (
          <div className="flex flex-wrap gap-1">
            {info.getValue<string[]>().map((c) => (
              <Badge key={c} {...badgeSem("neutral")}>
                {c}
              </Badge>
            ))}
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "状态",
        cell: (info) => {
          const status = info.getValue<ModelTarget["status"]>();
          return (
            <Badge {...badgeSem(modelTargetTone[status])}>{modelTargetStatusLabel[status]}</Badge>
          );
        },
      },
      {
        accessorKey: "circuitState",
        header: "熔断",
        cell: (info) => (
          <span className="font-mono text-[0.8125rem]">
            {circuitStateLabel[info.getValue<ModelTarget["circuitState"]>()]}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <div>
      <AdminPageHeader
        icon={Settings2}
        title="模型设置"
        description="查看模型目标的优先序、能力与熔断状态。"
      />
      <DataTable
        ariaLabel="模型目标列表"
        columns={columns}
        data={targets}
        loading={isPending}
        error={isError}
        onRetry={() => void refetch()}
        emptyTitle="暂无模型目标"
        emptyDescription="模型目标由摄取与聊天运行时按使用自动注册。"
      />
    </div>
  );
}
