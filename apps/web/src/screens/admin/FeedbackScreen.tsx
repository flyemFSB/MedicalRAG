// 反馈审核（CONTEXT.md：对回答的反馈，供运营复核答案质量）。
import { useQuery } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { useMemo, useState } from "react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { badgeSem } from "../../lib/status";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { FeedbackItem } from "../../lib/types";
import { feedbackQueryOptions } from "../../lib/queries";
import { relativeTime } from "../../lib/format";

export function FeedbackScreen() {
  const [value, setValue] = useState<"all" | "like" | "dislike">("all");
  const { data: items = [], isError, isPending, refetch } = useQuery(feedbackQueryOptions());

  const filtered = useMemo(
    () => (value === "all" ? items : items.filter((i) => i.value === value)),
    [items, value],
  );

  const columns = useMemo<ColumnDef<AppTableFeatures, FeedbackItem>[]>(
    () => [
      {
        accessorKey: "value",
        header: "反馈",
        cell: (info) => (
          <Badge {...badgeSem(info.getValue<string>() === "like" ? "success" : "warning")}>
            {info.getValue<string>() === "like" ? "赞" : "踩"}
          </Badge>
        ),
      },
      {
        accessorKey: "comment",
        header: "意见",
        cell: (info) => info.getValue<string>() ?? <span className="text-muted-foreground">—</span>,
      },
      {
        accessorKey: "messageId",
        header: "消息 ID",
        cell: (info) => (
          <span className="font-mono text-[0.8125rem]">{info.getValue<string>()}</span>
        ),
      },
      {
        accessorKey: "conversationId",
        header: "会话 ID",
        cell: (info) => (
          <span className="font-mono text-[0.8125rem]">{info.getValue<string>() ?? "—"}</span>
        ),
      },
      {
        accessorKey: "createdAt",
        header: "时间",
        cell: (info) => relativeTime(info.getValue<string>()),
      },
    ],
    [],
  );

  return (
    <div>
      <AdminPageHeader
        icon={MessageSquareText}
        title="反馈审核"
        description="复核用户对回答的反馈，定位答案质量短板。"
      />
      <div className="mb-3 flex items-center gap-3">
        <Select value={value} onValueChange={(v) => setValue(v as "all" | "like" | "dislike")}>
          <SelectTrigger aria-label="按反馈类型筛选" className="w-40">
            <SelectValue placeholder="全部反馈" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部反馈</SelectItem>
            <SelectItem value="like">赞</SelectItem>
            <SelectItem value="dislike">踩</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto" />
        <span className="text-caption text-muted-foreground">共 {items.length} 条反馈</span>
      </div>
      <DataTable
        ariaLabel="反馈列表"
        columns={columns}
        data={filtered}
        loading={isPending}
        error={isError}
        onRetry={() => void refetch()}
        emptyTitle="暂无反馈"
        emptyDescription="用户对回答点赞或点踩后，反馈会显示在这里。"
      />
    </div>
  );
}
