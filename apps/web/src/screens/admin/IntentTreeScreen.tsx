// 意图树配置（CONTEXT.md：配置的信息操作/系统动作；可折叠树编辑器 + 节点详情 +
// 新建/编辑对话框；树视/图形/列表三视图切换）。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Graph } from "@antv/g6";
import { useMemo, useState, useEffect, useRef, type FormEvent } from "react";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, GitBranch } from "lucide-react";
import { Badge } from "../../components/ui/badge";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { Textarea } from "../../components/ui/textarea";
import { Skeleton } from "../../components/ui/skeleton";
import { cn } from "../../lib/utils";
import type { IntentNode } from "../../lib/types";
import { adminKeys, adminMutations, intentTreeQueryOptions } from "../../lib/queries";

type View = "tree" | "graph" | "list";

const SAFETY_OPTIONS = ["treatment", "diagnosis", "urgent"];

// 意图树关系图（@antv/g6；读视图 + 节点选择，图数据由意图节点推导；内联于本屏）
function IntentTreeGraph({
  nodes,
  onSelect,
}: {
  nodes: IntentNode[];
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    if (nodes.length === 0) return;
    const data = {
      nodes: nodes.map((n) => ({ id: n.id, data: { name: n.name, enabled: n.enabled } })),
      edges: nodes
        .filter((n) => n.parentId)
        .map((n) => ({ source: n.parentId as string, target: n.id })),
    };
    const tokenColor = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const accent = tokenColor("--color-accent");
    const accentSoft = tokenColor("--color-accent-soft");
    const faint = tokenColor("--color-faint");
    const edgeStroke = tokenColor("--color-panel-strong");
    const graph = new Graph({
      container: containerRef.current,
      autoResize: true,
      data,
      layout: { type: "compact-box", direction: "LR", nodeSep: 24, rankSep: 48 },
      node: {
        style: {
          labelText: (d: any) => d.data?.name ?? d.id,
          labelPlacement: "right",
          labelWordWrap: true,
          labelMaxWidth: 160,
          fill: (d: any) => (d.data?.enabled === false ? faint : accentSoft),
          stroke: accent,
          lineWidth: 1,
        },
      },
      edge: { style: { stroke: edgeStroke, endArrow: true } },
      behaviors: ["drag-canvas", "zoom-canvas", "drag-element", "click-select"],
    });
    graph.render();
    graph.on("node:click", (evt: any) => onSelect(String(evt.target.id)));
    return () => {
      graph.destroy();
    };
  }, [nodes, onSelect]);

  return nodes.length === 0 ? (
    <div className="grid h-[480px] place-items-center rounded-md border border-dashed border-border text-body-sm text-muted-foreground">
      暂无意图节点，关系图将在有节点后显示。
    </div>
  ) : (
    <div ref={containerRef} style={{ width: "100%", height: 480 }} aria-label="意图树关系图" />
  );
}

export function IntentTreeScreen() {
  const [view, setView] = useState<View>("tree");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <GitBranch className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">意图树配置</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">
              配置意图层级、类型与节点关系。回答按命中的意图路由到检索或系统动作。
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Tabs value={view} onValueChange={(v) => setView(v as View)} className="items-center">
            <TabsList>
              <TabsTrigger value="tree">树状视图</TabsTrigger>
              <TabsTrigger value="graph">图形视图</TabsTrigger>
              <TabsTrigger value="list">列表视图</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>
      {view === "tree" ? (
        <TreeView selectedId={selectedId} onSelect={setSelectedId} />
      ) : view === "graph" ? (
        <GraphView selectedId={selectedId} onSelect={setSelectedId} />
      ) : (
        <ListView />
      )}
    </div>
  );
}

function GraphView({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const { data: nodes = [] } = useQuery(intentTreeQueryOptions());
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>意图树关系图</CardTitle>
          <p className="text-body-sm text-muted-foreground">拖动/滚轮缩放；点击节点查看详情</p>
        </CardHeader>
        <CardContent>
          <IntentTreeGraph nodes={nodes} onSelect={onSelect} />
        </CardContent>
      </Card>
      <NodeDetail key={selectedId ?? "none"} node={nodes.find((n) => n.id === selectedId)} nodes={nodes} />
    </div>
  );
}

function TreeView({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const { data: nodes = [] } = useQuery(intentTreeQueryOptions());
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
        <div
          role="button"
          tabIndex={0}
          aria-pressed={isSelected}
          onClick={() => onSelect(node.id)}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(node.id)}
          className={cn(
            "flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-body-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "hover:bg-panel",
            isSelected && "bg-accent-soft hover:bg-accent-soft",
            node.level === 0 && "font-semibold",
          )}
          style={{ paddingLeft: 8 + depth * 20 }}
        >
          {children.length > 0 ? (
            <button
              type="button"
              aria-label={isCollapsed ? "展开" : "收起"}
              className="grid size-6 shrink-0 place-items-center rounded-sm text-muted-foreground outline-none hover:bg-panel-strong focus-visible:ring-2 focus-visible:ring-ring"
              onClick={(e) => {
                e.stopPropagation();
                toggle(node.id);
              }}
            >
              {isCollapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
            </button>
          ) : (
            <span className="size-6 shrink-0" aria-hidden />
          )}
          <span className="min-w-0 flex-1 truncate text-ink">{node.name}</span>
          <Badge variant="neutral">{node.kind}</Badge>
          {node.safetyScope ? <Badge variant="error">{node.safetyScope}</Badge> : null}
          {!node.enabled ? <span className="text-caption text-muted-foreground">停用</span> : null}
        </div>
        {children.length > 0 && !isCollapsed ? children.map((child) => renderNode(child, depth + 1)) : null}
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
          {(byParent.get(null) ?? []).map((root) => renderNode(root, 0))}
        </CardContent>
      </Card>
      <NodeDetail key={selectedId ?? "none"} node={nodes.find((n) => n.id === selectedId)} nodes={nodes} />
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
          <Badge variant="neutral">{node.kind}</Badge>
          {parent ? <Badge variant="neutral">父节点: {parent.name}</Badge> : <Badge variant="neutral">根节点</Badge>}
          {node.safetyScope ? <Badge variant="error">安全边界: {node.safetyScope}</Badge> : null}
          <Badge variant={node.enabled ? "success" : "neutral"}>{node.enabled ? "启用" : "停用"}</Badge>
        </div>
        {node.description ? <p className="mb-4 text-body-sm text-muted-foreground">{node.description}</p> : null}
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
          <Button size="sm" disabled title="该操作待后端接入后可用">新建子节点</Button>
          <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>编辑</Button>
          <Button variant="ghost" size="sm" disabled title="该操作待后端接入后可用">删除</Button>
        </div>
      </CardContent>
      <NodeEditorDialog open={editOpen} onClose={() => setEditOpen(false)} node={node} nodes={nodes} />
    </Card>
  );
}

function ListView() {
  const { data: nodes = [], isPending } = useQuery(intentTreeQueryOptions());
  const [filter, setFilter] = useState("");

  const filtered = useMemo(
    () => nodes.filter((n) => n.name.toLowerCase().includes(filter.trim().toLowerCase())),
    [nodes, filter],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Input aria-label="搜索意图节点" placeholder="搜索节点名称…" className="w-64" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <div className="ml-auto" />
          <span className="text-caption text-muted-foreground">共 {nodes.length} 个节点</span>
        </div>
      </CardHeader>
      <CardContent>
        <Table aria-label="意图节点列表">
          <TableHeader>
            <TableRow>
              <TableHead>节点</TableHead>
              <TableHead>类型</TableHead>
              <TableHead>安全边界</TableHead>
              <TableHead className="text-right">示例数</TableHead>
              <TableHead>状态</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending
              ? Array.from({ length: 4 }, (_, i) => (
                  <TableRow key={i} className="hover:bg-transparent">
                    <TableCell colSpan={5}><Skeleton className="h-4 w-full" /></TableCell>
                  </TableRow>
                ))
              : filtered.map((node) => (
                  <TableRow key={node.id}>
                    <TableCell className="font-medium text-ink">{node.name}</TableCell>
                    <TableCell><Badge variant="neutral">{node.kind}</Badge></TableCell>
                    <TableCell>
                      {node.safetyScope ? <Badge variant="error">{node.safetyScope}</Badge> : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{node.examples.length}</TableCell>
                    <TableCell>
                      <Badge variant={node.enabled ? "success" : "neutral"}>{node.enabled ? "启用" : "停用"}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
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
  const [kind, setKind] = useState(node.kind);
  const [description, setDescription] = useState(node.description ?? "");
  const [examples, setExamples] = useState(() => node.examples.join("\n"));
  const [safetyScope, setSafetyScope] = useState(node.safetyScope ?? "");
  const [enabled, setEnabled] = useState(node.enabled);
  const [parentId, setParentId] = useState(node.parentId ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () =>
      adminMutations.updateIntentNode(node.id, {
        name: name.trim(),
        description: description.trim(),
        examples: examples.split("\n").map((s) => s.trim()).filter(Boolean),
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
                <p id="in-name-error" className="text-caption text-error">{nameError}</p>
              ) : null}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="in-kind">类型</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger id="in-kind"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="leaf">检索/动作</SelectItem>
                  <SelectItem value="system">系统交互</SelectItem>
                  <SelectItem value="group">分组</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-parent">父节点</Label>
            <Select value={parentId} onValueChange={setParentId}>
              <SelectTrigger id="in-parent"><SelectValue placeholder="根节点" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">根节点</SelectItem>
                {nodes.filter((n) => n.id !== node.id).map((n) => (
                  <SelectItem key={n.id} value={n.id}>{n.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-safety">安全边界</Label>
            <Select value={safetyScope} onValueChange={setSafetyScope}>
              <SelectTrigger id="in-safety"><SelectValue placeholder="无（普通检索）" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">无（普通检索）</SelectItem>
                {SAFETY_OPTIONS.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-caption text-muted-foreground">命中该意图时展示的安全提醒范围；仅高风险意图需要。</p>
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
            <p className="text-caption text-muted-foreground">每行一个示例问题，用于意图分类训练。</p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="in-desc">描述</Label>
            <Textarea id="in-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <div className="flex items-center gap-3">
            <Switch id="in-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="in-enabled" className="text-body">启用节点</Label>
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
