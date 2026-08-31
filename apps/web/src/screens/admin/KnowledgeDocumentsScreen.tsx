// 文档管理（CONTEXT.md：原始来源；摄取状态徽章 + 分块入口）。
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Boxes, ChevronRight, FileImage, FileSpreadsheet, FileText, FolderOpen } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
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
import type { Document } from "../../lib/types";
import { documentsQueryOptions, knowledgeBasesQueryOptions } from "../../lib/queries";
import { formatBytes, formatDateTime, formatLabel, ingestionStatusLabel, ingestionStatusTone } from "../../lib/format";

export const Route = createFileRoute("/admin/knowledge/$kbId")({
  component: KnowledgeDocumentsScreen,
});

export function KnowledgeDocumentsScreen() {
  const { kbId } = Route.useParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const { data: kbList = [] } = useQuery(knowledgeBasesQueryOptions());
  const kb = kbList.find((k) => k.id === kbId);
  const { data: docs = [], isPending } = useQuery(documentsQueryOptions(kbId));

  const filtered = useMemo(
    () =>
      docs.filter(
        (d) =>
          (status === "all" || d.ingestionStatus === status) &&
          d.title.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [docs, status, query],
  );

  const columns = useMemo<ColumnDef<AppTableFeatures, Document>[]>(
    () => [
      {
        accessorKey: "title",
        header: "文档",
        cell: (info) => {
          const doc = info.row.original;
          return (
            <div className="flex items-start gap-2">
              <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md bg-panel text-muted-foreground">
                <FormatIcon format={doc.format} />
              </span>
              <div className="min-w-0">
                <Link
                  to="/admin/knowledge/$kbId/docs/$docId"
                  params={{ kbId, docId: doc.id }}
                  className="rounded-sm font-medium text-ink outline-none focus-visible:ring-2 focus-visible:ring-ring hover:text-accent-ink"
                >
                  {doc.title}
                </Link>
                <div className="text-caption text-muted-foreground">
                  {formatLabel[doc.format] ?? doc.format} · {formatBytes(doc.sizeBytes)} · 本地来源
                </div>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: "ingestionStatus",
        header: "状态",
        cell: (info) => (
          <Badge variant={ingestionStatusTone[info.getValue<string>()] ?? "neutral"}>
            {ingestionStatusLabel[info.getValue<string>()] ?? info.getValue<string>()}
          </Badge>
        ),
      },
      { accessorKey: "chunkCount", header: "分块数", cell: (info) => <span className="tabular-nums">{info.getValue<number>()}</span> },
      { accessorKey: "createdAt", header: "创建时间", cell: (info) => <span className="whitespace-nowrap">{formatDateTime(info.getValue<string>())}</span> },
    ],
    [kbId],
  );

  return (
    <div>
      <nav aria-label="面包屑" className="mb-3 flex items-center gap-1.5 text-caption text-muted-foreground">
        <Link to="/admin/knowledge" className="rounded-sm font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">
          知识库管理
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="min-w-0 truncate">{kb ? kb.name : "文档管理"}</span>
      </nav>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <FolderOpen className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">文档管理</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">
              {kb ? `${kb.name}（${kb.id}）` : "知识库文档"}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" onClick={() => navigate({ to: "/admin/knowledge" })}>返回知识库</Button>
          <Button disabled title="该操作待后端接入后可用">上传文档</Button>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Input
          aria-label="搜索文档名称"
          placeholder="搜索文档名称"
          className="w-60"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label="按摄取状态筛选" className="w-40">
            <SelectValue placeholder="全部状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="published">已发布</SelectItem>
            <SelectItem value="indexing">索引中</SelectItem>
            <SelectItem value="validating">校验中</SelectItem>
            <SelectItem value="failed">失败</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto" />
        <span className="text-caption text-muted-foreground">共 {docs.length} 篇文档</span>
      </div>
      <DataTable
        ariaLabel="文档列表"
        columns={columns}
        data={filtered}
        loading={isPending}
        emptyTitle="暂无文档"
        emptyDescription="上传功能接入后，可导入第一份受支持格式的医疗来源。"
        renderRowActions={(doc) => (
          <Button variant="ghost" size="icon" aria-label="查看分块" asChild>
            <Link to="/admin/knowledge/$kbId/docs/$docId" params={{ kbId, docId: doc.id }}>
              <Boxes />
            </Link>
          </Button>
        )}
      />
    </div>
  );
}

/** 文档格式图标（支持格式见 CONTEXT.md Supported Source）。 */
function FormatIcon({ format }: { format: string }) {
  const Icon =
    format === "xlsx"
      ? FileSpreadsheet
      : format === "png" || format === "jpg" || format === "jpeg"
        ? FileImage
        : FileText;
  return <Icon className="size-3.5" aria-hidden />;
}
