// 查询术语映射（CONTEXT.md：把用户表述归一化到意图节点的映射规则）。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, Pencil, Trash2 } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Badge } from "../../components/ui/badge";
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
import type { QueryTermMapping } from "../../lib/types";
import { adminKeys, adminMutations, intentTreeQueryOptions, mappingsQueryOptions } from "../../lib/queries";
import { relativeTime } from "../../lib/format";

export function MappingsScreen() {
  const [addOpen, setAddOpen] = useState(false);
  const { data: mappings = [], isPending } = useQuery(mappingsQueryOptions());
  const { data: nodes = [] } = useQuery(intentTreeQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, QueryTermMapping>[]>(
    () => [
      { accessorKey: "term", header: "术语", cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span> },
      {
        id: "intent",
        header: "目标意图",
        cell: (info) => {
          const mapping = info.row.original;
          return nodes.find((n) => n.id === mapping.intentNodeId)?.name ?? mapping.intentNodeId;
        },
      },
      {
        accessorKey: "enabled",
        header: "状态",
        cell: (info) => <Badge variant={info.getValue<boolean>() ? "success" : "neutral"}>{info.getValue<boolean>() ? "启用" : "停用"}</Badge>,
      },
      { accessorKey: "createdAt", header: "创建时间", cell: (info) => relativeTime(info.getValue<string>()) },
    ],
    [nodes],
  );

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <ArrowRightLeft className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">查询术语映射</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">配置查询归一化的关键词映射规则，把用户表述定向到正确意图。</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button onClick={() => setAddOpen(true)}>新增映射</Button>
        </div>
      </div>
      <div className="mb-3 flex items-center gap-3">
        <Input aria-label="搜索术语" placeholder="搜索术语…" className="w-60" />
        <div className="ml-auto" />
        <span className="text-caption text-muted-foreground">共 {mappings.length} 条映射</span>
      </div>
      <DataTable
        ariaLabel="查询术语映射列表"
        columns={columns}
        data={mappings}
        loading={isPending}
        emptyTitle="暂无映射"
        emptyDescription="添加术语映射，让用户表述命中正确的意图节点。"
        renderRowActions={() => (
          <>
            <Button variant="ghost" size="icon" aria-label="编辑映射" disabled title="该操作待后端接入后可用">
              <Pencil />
            </Button>
            <Button variant="ghost" size="icon" aria-label="删除映射" disabled title="该操作待后端接入后可用">
              <Trash2 />
            </Button>
          </>
        )}
      />
      <AddMappingDialog open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

function AddMappingDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: nodes = [] } = useQuery(intentTreeQueryOptions());
  const [term, setTerm] = useState("");
  const [intentNodeId, setIntentNodeId] = useState("");
  const [termError, setTermError] = useState<string | null>(null);
  const [intentError, setIntentError] = useState<string | null>(null);
  const termRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () => adminMutations.createMapping({ term: term.trim(), intentNodeId }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.mappings });
      toast.success("映射已新增");
      setTerm("");
      setIntentNodeId("");
      onClose();
    },
    onError: () => toast.error("新增失败"),
  });

  function validateAndSubmit() {
    const t = !term.trim();
    const i = !intentNodeId;
    setTermError(t ? "请输入术语" : null);
    setIntentError(i ? "请选择目标意图" : null);
    if (t) {
      termRef.current?.focus();
      return;
    }
    if (i) return;
    mutation.mutate();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    validateAndSubmit();
  }

  const leafNodes = nodes.filter((n) => n.kind !== "root" && n.kind !== "group");

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增映射规则</DialogTitle>
          <DialogDescription>把用户表述中的关键词定向到正确的意图节点。</DialogDescription>
        </DialogHeader>
        <form id="mapping-form" onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="map-term">术语</Label>
            <Input
              id="map-term"
              ref={termRef}
              value={term}
              onChange={(e) => {
                setTerm(e.target.value);
                if (termError) setTermError(null);
              }}
              required
              placeholder="例如：降压"
              aria-invalid={termError ? true : undefined}
              aria-describedby={termError ? "map-term-error" : undefined}
            />
            <p className="text-caption text-muted-foreground">用户在问题中使用的表述，例如"降压"。</p>
            {termError ? (
              <p id="map-term-error" className="text-caption text-error">{termError}</p>
            ) : null}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="map-intent">目标意图</Label>
            <Select value={intentNodeId} onValueChange={(v) => {
              setIntentNodeId(v);
              if (intentError) setIntentError(null);
            }}>
              <SelectTrigger id="map-intent" className="w-full">
                <SelectValue placeholder="选择意图节点…" />
              </SelectTrigger>
              <SelectContent>
                {leafNodes.map((n) => (
                  <SelectItem key={n.id} value={n.id}>{n.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {intentError ? (
              <p id="map-intent-error" className="text-caption text-error">{intentError}</p>
            ) : null}
          </div>
        </form>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button type="button" onClick={validateAndSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
