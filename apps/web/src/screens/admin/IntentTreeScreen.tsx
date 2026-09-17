// 意图树配置（CONTEXT.md：配置的信息操作/系统动作；可折叠树编辑器 + 节点详情 +
// 新建/编辑对话框；树视/列表双视图切换）。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState, useRef, type FormEvent } from "react";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, GitBranch } from "lucide-react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { DataTable } from "../../components/data-table";
import type { AppTableFeatures } from "../../lib/table";
import { badgeSem } from "../../lib/status";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
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
import { Switch } from "../../components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { Textarea } from "../../components/ui/textarea";
import { cn } from "../../lib/utils";
import type { IntentNode } from "../../lib/types";
import { adminKeys, intentTreeQueryOptions } from "../../lib/queries";
import { updateIntentNode } from "../../lib/api";

type View = "tree" | "list";

const SAFETY_OPTIONS = ["treatment", "diagnosis", "urgent"];

export function IntentTreeScreen() {
  const [view, setView] = useState<View>("tree");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div>
      <AdminPageHeader
        icon={GitBranch}
        title="意图树配置"
        description="配置意图层级、类型与节点关系。回答按命中的意图路由到检索或系统动作。"
        actions={
          <Tabs value={view} onValueChange={(v) => setView(v as View)} className="items-center">
            <TabsList>
              <TabsTrigger value="tree">树状视图</TabsTrigger>
              <TabsTrigger value="list">列表视图</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />
      {view === "tree" ? (
        <TreeView selectedId={selectedId} onSelect={setSelectedId} />
      ) : (
        <ListView />
      )}
    </div>
  );
}

function TreeView({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: nodes = [], isError } = useQuery(intentTreeQueryOptions());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const byParent = useMemo(() => {
    const map = new Map<string | null, IntentNode[]>();
    for (const node of nodes) map.set(node.parentId, [...(map.get(node.parentId) ?? []), node]);
    return map;
  }, [nodes]);

  function toggle(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderNode(node: IntentNode, depth: number) {
    const children = byParent.get(node.id) ?? [];
    const isCollapsed = collapsed.has(node.id);
    const isSelected = selectedId === node.id;
    return (
      <div key={node.id}>
        {/* 行内不再嵌套交互元素：展开按钮与选中按钮为同级真实 button（避免 role=button 包裹 button） */}
        <div
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-body-sm",
            isSelected && "bg-accent-soft",
            node.level === 0 && "font-semibold",
          )}
          style={{ paddingLeft: 8 + depth * 20 }}
        >
          {children.length > 0 ? (
            <button
              type="button"
              aria-label={isCollapsed ? "展开" : "收起"}
              aria-expanded={!isCollapsed}
              className="grid size-6 shrink-0 place-items-center rounded-sm text-muted-foreground outline-none hover:bg-panel-strong focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => toggle(node.id)}
            >
              {isCollapsed ? (
                <ChevronRight className="size-4" />
              ) : (
                <ChevronDown className="size-4" />
              )}
            </button>
          ) : (
            <span className="size-6 shrink-0" aria-hidden />
          )}
          <button
            type="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(node.id)}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-sm text-left outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="min-w-0 flex-1 truncate text-ink">{node.name}</span>
            <Badge {...badgeSem("neutral")}>{node.kind}</Badge>
            {node.safetyScope ? <Badge {...badgeSem("error")}>{node.safetyScope}</Badge> : null}
            {!node.enabled ? (
              <span className="text-caption text-muted-foreground">停用</span>
            ) : null}
          </button>
        </div>
        {children.length > 0 && !isCollapsed
          ? children.map((child) => renderNode(child, depth + 1))
          : null}
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>意图树结构</CardTitle>
          <p className="text-body-sm text-muted-foreground">点击节点查看详情</p>
        </CardHeader>
        <CardContent>
          {isError ? (
            <p role="alert" className="text-body-sm text-destructive">
              意图树加载失败，请刷新页面重试
            </p>
          ) : (
            (byParent.get(null) ?? []).map((root) => renderNode(root, 0))
          )}
        </CardContent>
      </Card>
      <NodeDetail
        key={selectedId ?? "none"}
        node={nodes.find((n) => n.id === selectedId)}
        nodes={nodes}
      />
    </div>
  );
}

function NodeDetail({ node, nodes }: { node: IntentNode | undefined; nodes: IntentNode[] }) {
  const [editOpen, setEditOpen] = useState(false);
  if (!node) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>节点详情</CardTitle>
        </CardHeader>
        <CardContent className="text-body-sm text-muted-foreground">
          从左侧选择一个节点查看详情。
        </CardContent>
      </Card>
    );
  }
  const parent = nodes.find((n) => n.id === node.parentId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>节点详情</CardTitle>
        <p className="text-body-sm text-muted-foreground">{node.name}</p>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge {...badgeSem("neutral")}>{node.kind}</Badge>
          {parent ? (
            <Badge {...badgeSem("neutral")}>父节点: {parent.name}</Badge>
          ) : (
            <Badge {...badgeSem("neutral")}>根节点</Badge>
          )}
          {node.safetyScope ? (
            <Badge {...badgeSem("error")}>安全边界: {node.safetyScope}</Badge>
          ) : null}
          <Badge {...badgeSem(node.enabled ? "success" : "neutral")}>
            {node.enabled ? "启用" : "停用"}
          </Badge>
        </div>
        {node.description ? (
          <p className="mb-4 text-body-sm text-muted-foreground">{node.description}</p>
        ) : null}
        {node.examples.length > 0 ? (
          <div className="mb-4">
            <p className="mb-1.5 text-body-sm font-medium text-body">示例问题</p>
            <ul className="grid list-inside list-disc gap-1 text-body-sm text-body">
              {node.examples.map((ex) => (
                <li key={ex}>{ex}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
            编辑
          </Button>
        </div>
      </CardContent>
      <NodeEditorDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        node={node}
        nodes={nodes}
      />
    </Card>
  );
}

const listColumns: ColumnDef<AppTableFeatures, IntentNode>[] = [
  {
    accessorKey: "name",
    header: "节点",
    cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span>,
  },
  {
    accessorKey: "kind",
    header: "类型",
    cell: (info) => <Badge {...badgeSem("neutral")}>{info.getValue<string>()}</Badge>,
  },
  {
    accessorKey: "safetyScope",
    header: "安全边界",
    cell: (info) =>
      info.getValue<string | undefined>() ? (
        <Badge {...badgeSem("error")}>{info.getValue<string>()}</Badge>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: "examples",
    header: "示例数",
    cell: (info) => (
      <span className="block text-right tabular-nums">{info.getValue<string[]>().length}</span>
    ),
  },
  {
    accessorKey: "enabled",
    header: "状态",
    cell: (info) => (
      <Badge {...badgeSem(info.getValue<boolean>() ? "success" : "neutral")}>
        {info.getValue<boolean>() ? "启用" : "停用"}
      </Badge>
    ),
  },
];

function ListView() {
  const { data: nodes = [], isError, isPending, refetch } = useQuery(intentTreeQueryOptions());
  const [filter, setFilter] = useState("");

  const filtered = useMemo(
    () => nodes.filter((n) => n.name.toLowerCase().includes(filter.trim().toLowerCase())),
    [nodes, filter],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Input
            aria-label="搜索意图节点"
            placeholder="搜索节点名称…"
            className="w-64"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="ml-auto" />
          <span className="text-caption text-muted-foreground">共 {nodes.length} 个节点</span>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable
          ariaLabel="意图节点列表"
          columns={listColumns}
          data={filtered}
          loading={isPending}
          error={isError}
          onRetry={() => void refetch()}
          emptyTitle="暂无意图节点"
          emptyDescription="先在上方树视图中新建意图节点。"
        />
      </CardContent>
    </Card>
  );
}

function NodeEditorDialog({
  open,
  onClose,
  node,
  nodes,
}: {
  open: boolean;
  onClose: () => void;
  node: IntentNode;
  nodes: IntentNode[];
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(node.name);
  const [kind, setKind] = useState(node.kind === "system" ? "system" : "knowledge");
  const [description, setDescription] = useState(node.description ?? "");
  const [examples, setExamples] = useState(() => node.examples.join("\n"));
  const [safetyScope, setSafetyScope] = useState(node.safetyScope ?? "");
  const [enabled, setEnabled] = useState(node.enabled);
  const [parentId, setParentId] = useState(node.parentId ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () =>
      updateIntentNode(node.id, {
        name: name.trim(),
        description: description.trim(),
        examples: examples
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        safetyScope: safetyScope || undefined,
        enabled,
        kind,
        parentId: parentId || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.intentTree });
      toast.success("节点已保存");
      onClose();
    },
    onError: () => toast.error("保存失败"),
  });

  function validateAndSubmit() {
    if (!name.trim()) {
      setNameError("请输入节点名称");
      nameRef.current?.focus();
      return;
    }
    setNameError(null);
    mutation.mutate();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    validateAndSubmit();
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑意图节点</DialogTitle>
          <DialogDescription>配置节点名称、类型、示例问题与安全边界。</DialogDescription>
        </DialogHeader>
        <form id="intent-node-form" onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="in-name">节点名称</Label>
              <Input
                id="in-name"
                ref={nameRef}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (nameError) setNameError(null);
                }}
                required
                maxLength={50}
                aria-invalid={nameError ? true : undefined}
                aria-describedby={nameError ? "in-name-error" : undefined}
              />
              {nameError ? (
                <p id="in-name-error" className="text-caption text-error">
                  {nameError}
                </p>
              ) : null}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="in-kind">类型</Label>
              <Select value={kind} onValueChange={(v) => setKind(v ?? "")}>
                <SelectTrigger id="in-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="knowledge">知识检索</SelectItem>
                  <SelectItem value="system">系统交互</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-parent">父节点</Label>
            <Select value={parentId} onValueChange={(v) => setParentId(v ?? "")}>
              <SelectTrigger id="in-parent">
                <SelectValue placeholder="根节点" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">根节点</SelectItem>
                {nodes
                  .filter((n) => n.id !== node.id)
                  .map((n) => (
                    <SelectItem key={n.id} value={n.id}>
                      {n.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-safety">安全边界</Label>
            <Select value={safetyScope} onValueChange={(v) => setSafetyScope(v ?? "")}>
              <SelectTrigger id="in-safety">
                <SelectValue placeholder="无（普通检索）" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">无（普通检索）</SelectItem>
                {SAFETY_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-caption text-muted-foreground">
              命中该意图时展示的安全提醒范围；仅高风险意图需要。
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-examples">示例问题</Label>
            <Textarea
              id="in-examples"
              value={examples}
              onChange={(e) => setExamples(e.target.value)}
              rows={4}
              placeholder={"高血压降压目标是多少\n二甲双胍能和阿卡波糖一起用吗"}
            />
            <p className="text-caption text-muted-foreground">
              每行一个示例问题，用于意图分类训练。
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-desc">描述</Label>
            <Textarea
              id="in-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch id="in-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="in-enabled" className="text-body">
              启用节点
            </Label>
          </div>
        </form>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button type="button" onClick={validateAndSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
