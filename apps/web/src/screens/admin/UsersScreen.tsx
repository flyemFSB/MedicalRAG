// 用户与工作区管理（CONTEXT.md：用户是经过鉴权的个人账户；工作区是隔离范围）。
import { useQuery } from "@tanstack/react-query";
import { Ban, Pencil, Users } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { User } from "../../lib/types";
import { usersQueryOptions, workspacesQueryOptions } from "../../lib/queries";
import { relativeTime } from "../../lib/format";

export function UsersScreen() {
  const { data: users = [], isPending } = useQuery(usersQueryOptions());
  const { data: workspaces = [] } = useQuery(workspacesQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, User>[]>(
    () => [
      { accessorKey: "email", header: "用户", cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span> },
      {
        accessorKey: "role",
        header: "角色",
        cell: (info) => <Badge variant={info.getValue<string>() === "admin" ? "info" : "neutral"}>{info.getValue<string>() === "admin" ? "管理员" : "成员"}</Badge>,
      },
      {
        accessorKey: "status",
        header: "状态",
        cell: (info) => <Badge variant={info.getValue<string>() === "active" ? "success" : "neutral"}>{info.getValue<string>() === "active" ? "启用" : "停用"}</Badge>,
      },
    ],
    [],
  );

  return (
    <div>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-panel text-muted-foreground">
            <Users className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-heading-lg font-semibold text-ink">用户与工作区</h1>
            <p className="mt-1 max-w-[60ch] text-body-sm text-muted-foreground">管理后台账号与角色权限，维护工作区成员与隔离范围。</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button disabled title="该操作待后端接入后可用">新增用户</Button>
        </div>
      </div>
      <div className="mb-3 flex items-center">
        <span className="ml-auto text-caption text-muted-foreground">共 {users.length} 个用户 · {workspaces.length} 个工作区</span>
      </div>
      <DataTable
        ariaLabel="用户列表"
        columns={columns}
        data={users}
        loading={isPending}
        emptyTitle="暂无用户"
        emptyDescription="添加第一个后台账号，开始运营这个知识工作台。"
        renderRowActions={() => (
          <>
            <Button variant="ghost" size="icon" aria-label="编辑用户" disabled title="该操作待后端接入后可用">
              <Pencil />
            </Button>
            <Button variant="ghost" size="icon" aria-label="停用用户" disabled title="该操作待后端接入后可用">
              <Ban />
            </Button>
          </>
        )}
      />
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>工作区</CardTitle>
          <p className="text-body-sm text-muted-foreground">成员共享知识库、会话与运营记录的隔离范围</p>
        </CardHeader>
        <CardContent>
          <Table aria-label="工作区列表">
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead className="text-right">成员数</TableHead>
                <TableHead>创建时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {workspaces.map((ws) => (
                <TableRow key={ws.id}>
                  <TableCell className="font-medium text-ink">{ws.name}</TableCell>
                  <TableCell className="text-right tabular-nums">{ws.memberCount}</TableCell>
                  <TableCell>{relativeTime(ws.createdAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
