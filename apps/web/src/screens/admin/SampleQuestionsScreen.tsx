// 样例问题（CONTEXT.md：欢迎页的推荐问题配置）。
import { useQuery } from "@tanstack/react-query";
import { ListChecks, Pencil, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { SampleQuestion } from "../../lib/types";
import { sampleQuestionsQueryOptions } from "../../lib/queries";
import { relativeTime } from "../../lib/format";

export function SampleQuestionsScreen() {
  const [filter, setFilter] = useState("");
  const { data: questions = [], isPending } = useQuery(sampleQuestionsQueryOptions());

  const filtered = useMemo(
    () => questions.filter((q) => q.text.toLowerCase().includes(filter.trim().toLowerCase())),
    [questions, filter],
  );

  const columns = useMemo<ColumnDef<AppTableFeatures, SampleQuestion>[]>(
    () => [
      { accessorKey: "text", header: "示例问题", cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span> },
      {
        accessorKey: "enabled",
        header: "状态",
        cell: (info) => <Badge variant={info.getValue<boolean>() ? "success" : "neutral"}>{info.getValue<boolean>() ? "启用" : "停用"}</Badge>,
      },
      { accessorKey: "createdAt", header: "更新时间", cell: (info) => relativeTime(info.getValue<string>()) },
    ],
    [],
  );

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <ListChecks className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">样例问题</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">配置欢迎页的推荐问题，引导用户以循证方式提问。</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button disabled title="该操作待后端接入后可用">新增示例</Button>
        </div>
      </div>
      <div className="mb-3 flex items-center gap-3">
        <Input
          aria-label="搜索样例问题"
          placeholder="搜索问题…"
          className="w-60"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <div className="ml-auto" />
        <span className="text-caption text-muted-foreground">共 {questions.length} 个问题</span>
      </div>
      <DataTable
        ariaLabel="样例问题列表"
        columns={columns}
        data={filtered}
        loading={isPending}
        emptyTitle="暂无样例问题"
        emptyDescription="新增几个高频循证问题，让用户在欢迎页一键开始。"
        renderRowActions={() => (
          <>
            <Button variant="ghost" size="icon" aria-label="编辑示例" disabled title="该操作待后端接入后可用">
              <Pencil />
            </Button>
            <Button variant="ghost" size="icon" aria-label="删除示例" disabled title="该操作待后端接入后可用">
              <Trash2 />
            </Button>
          </>
        )}
      />
    </div>
  );
}
