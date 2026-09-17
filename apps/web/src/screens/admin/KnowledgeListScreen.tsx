// 知识库管理（CONTEXT.md：用户作用域的医疗来源集合；列表 + 新建对话框）。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Database } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { KnowledgeBase } from "../../lib/types";
import { adminKeys, knowledgeBasesQueryOptions } from "../../lib/queries";
import { createKnowledgeBase } from "../../lib/api";
import { relativeTime } from "../../lib/format";

export function KnowledgeListScreen() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const { data = [], isError, isPending, refetch } = useQuery(knowledgeBasesQueryOptions());

  const createMutation = useMutation({
    mutationFn: createKnowledgeBase,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.knowledgeBases });
      setCreateOpen(false);
      toast.success("知识库已创建");
    },
    onError: () => toast.error("创建失败，请稍后重试"),
  });

  const filtered = useMemo(
    () => data.filter((kb) => kb.name.toLowerCase().includes(query.trim().toLowerCase())),
    [data, query],
  );

  const columns = useMemo<ColumnDef<AppTableFeatures, KnowledgeBase>[]>(
    () => [
      {
        accessorKey: "name",
        header: "名称",
        cell: (info) => (
          <Link
            to="/admin/knowledge/$kbId"
            params={{ kbId: info.row.original.id }}
            className="rounded-sm font-medium text-ink outline-none focus-visible:ring-2 focus-visible:ring-ring hover:text-accent-ink"
          >
            {info.getValue<string>()}
          </Link>
        ),
      },
      {
        accessorKey: "documentCount",
        header: "文档数",
        cell: (info) => <span className="tabular-nums">{info.getValue<number>()}</span>,
      },
      {
        accessorKey: "updatedAt",
        header: "更新时间",
        cell: (info) => relativeTime(info.getValue<string>()),
      },
    ],
    [],
  );

  return (
    <div>
      <AdminPageHeader
        icon={Database}
        title="知识库管理"
        description="管理所有知识库及其文档。上传的医疗来源经摄取后成为可检索的分块。"
        actions={<Button onClick={() => setCreateOpen(true)}>新建知识库</Button>}
      />
      <div className="mb-3 flex items-center gap-3">
        <Input
          aria-label="搜索知识库名称"
          placeholder="搜索知识库名称"
          className="w-60"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="ml-auto" />
        <span className="text-caption text-muted-foreground">共 {data.length} 个知识库</span>
      </div>
      <DataTable
        ariaLabel="知识库列表"
        columns={columns}
        data={filtered}
        loading={isPending}
        error={isError}
        onRetry={() => void refetch()}
        emptyTitle={query ? "没有匹配的知识库" : "还没有知识库"}
        emptyDescription={
          query ? "换个关键词试试。" : "点击右上角「新建知识库」，导入第一批医疗来源。"
        }
      />

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={(input) => createMutation.mutate(input)}
        pending={createMutation.isPending}
      />
    </div>
  );
}

function CreateKnowledgeBaseDialog({
  open,
  onClose,
  onSubmit,
  pending,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (input: { name: string; description: string }) => void;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  function validateAndSubmit() {
    if (!name.trim()) {
      setNameError("请输入知识库名称");
      nameRef.current?.focus();
      return;
    }
    setNameError(null);
    onSubmit({ name: name.trim(), description: description.trim() });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    validateAndSubmit();
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建知识库</DialogTitle>
          <DialogDescription>为知识库起一个易于识别的名称，并说明其覆盖的主题。</DialogDescription>
        </DialogHeader>
        <form id="create-kb-form" onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="kb-name">知识库名称</Label>
            <Input
              id="kb-name"
              ref={nameRef}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (nameError) setNameError(null);
              }}
              required
              maxLength={50}
              placeholder="例如：心血管疾病循证资料"
              aria-invalid={nameError ? true : undefined}
              aria-describedby={nameError ? "kb-name-error" : undefined}
            />
            {nameError ? (
              <p id="kb-name-error" className="text-caption text-error">
                {nameError}
              </p>
            ) : null}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="kb-desc">描述</Label>
            <Textarea
              id="kb-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="这个知识库覆盖哪些主题？"
            />
          </div>
        </form>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button type="button" onClick={validateAndSubmit} disabled={pending}>
            {pending ? "创建中…" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
