// 用户与工作区管理（CONTEXT.md：用户是经过鉴权的个人账户；工作区是隔离范围）。
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Users } from "lucide-react";
import { useMemo } from "react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { DataTable } from "../../components/data-table";
import type { AppTableFeatures } from "../../lib/table";
import type { User, Workspace } from "../../lib/types";
import { usersQueryOptions, workspacesQueryOptions } from "../../lib/queries";
import { relativeTime } from "../../lib/format";

const workspaceColumns: ColumnDef<AppTableFeatures, Workspace>[] = [
  {
    accessorKey: "name",
    header: "名称",
    cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span>,
  },
  {
    accessorKey: "memberCount",
    header: "成员数",
    cell: (info) => (
      <span className="block text-right tabular-nums">{info.getValue<number>()}</span>
    ),
  },
  {
    accessorKey: "createdAt",
    header: "创建时间",
    cell: (info) => relativeTime(info.getValue<string>()),
  },
];

export function UsersScreen() {
  const { data: users = [], isError, isPending, refetch } = useQuery(usersQueryOptions());
  const {
    data: workspaces = [],
    isError: workspacesError,
    isPending: workspacesPending,
    refetch: workspacesRefetch,
  } = useQuery(workspacesQueryOptions());

  const columns = useMemo<ColumnDef<AppTableFeatures, User>[]>(
    () => [
      {
        accessorKey: "email",
        header: "用户",
        cell: (info) => <span className="font-medium text-ink">{info.getValue<string>()}</span>,
      },
      {
        accessorKey: "createdAt",
        header: "注册时间",
        cell: (info) => relativeTime(info.getValue<string>()),
      },
    ],
    [],
  );

  return (
    <div>
      <AdminPageHeader
        icon={Users}
        title="用户与工作区"
        description="管理后台账号与角色权限，维护工作区成员与隔离范围。"
      />
      <div className="mb-3 flex items-center">
        <span className="ml-auto text-caption text-muted-foreground">
          共 {users.length} 个用户 · {workspaces.length} 个工作区
        </span>
      </div>
      <DataTable
        ariaLabel="用户列表"
        columns={columns}
        data={users}
        loading={isPending}
        error={isError}
        onRetry={() => void refetch()}
        emptyTitle="暂无用户"
        emptyDescription="添加第一个后台账号，开始运营这个知识工作台。"
      />
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>工作区</CardTitle>
          <p className="text-body-sm text-muted-foreground">
            成员共享知识库、会话与运营记录的隔离范围
          </p>
        </CardHeader>
        <CardContent>
          <DataTable
            ariaLabel="工作区列表"
            columns={workspaceColumns}
            data={workspaces}
            loading={workspacesPending}
            error={workspacesError}
            onRetry={() => void workspacesRefetch()}
            emptyTitle="暂无工作区"
            emptyDescription="用户首次登录时自动创建个人工作区。"
          />
        </CardContent>
      </Card>
    </div>
  );
}
