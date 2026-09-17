"""身份与凭据持久化仓储（自 operator.py 按领域聚合拆分；组合门面见 operator.py）。"""

from __future__ import annotations

import typing
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.identity.workspace import (
    Role,
    UserMemberships,
    Workspace,
    WorkspaceMember,
)

from .models import (
    User,
    WorkspaceMemberRow,
    WorkspaceRow,
)


class SqlWorkspaceRepository:
    """工作区持久化仓储：实现 medical_core.identity.workspace.WorkspaceRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, workspace: Workspace) -> None:
        async with self._sessions() as session:
            session.add(WorkspaceRow(id=uuid.UUID(workspace.id), name=workspace.name))
            await session.commit()

    async def list_all_with_members(self) -> tuple[tuple[Workspace, int], ...]:
        """运营管理控制台：全量工作区及其成员数（单次分组聚合，避免逐工作区发查询）。"""
        async with self._sessions() as session:
            member_rows = (
                await session.execute(
                    select(WorkspaceMemberRow.workspace_id, func.count()).group_by(
                        WorkspaceMemberRow.workspace_id
                    )
                )
            ).all()
            counts: dict[uuid.UUID, int] = {wid: int(total) for wid, total in member_rows}
            rows = (
                await session.scalars(select(WorkspaceRow).order_by(WorkspaceRow.created_at))
            ).all()
            return tuple(
                (
                    Workspace(id=str(row.id), name=row.name, created_at=str(row.created_at)),
                    counts.get(row.id, 0),
                )
                for row in rows
            )


class SqlMembershipRepository:
    """工作区成员资格持久化仓储：实现 MembershipRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, member: WorkspaceMember) -> None:
        async with self._sessions() as session:
            session.add(
                WorkspaceMemberRow(
                    user_id=uuid.UUID(member.user_id),
                    workspace_id=uuid.UUID(member.workspace_id),
                    role=member.role.value,
                )
            )
            await session.commit()

    async def memberships_of(self, user_id: str) -> UserMemberships:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(WorkspaceMemberRow).where(
                        WorkspaceMemberRow.user_id == uuid.UUID(user_id)
                    )
                )
            ).all()
            return UserMemberships(
                user_id=user_id,
                memberships=tuple(
                    WorkspaceMember(
                        user_id=str(r.user_id),
                        workspace_id=str(r.workspace_id),
                        role=Role(r.role),
                    )
                    for r in rows
                ),
            )

    async def set_role(self, user_id: str, workspace_id: str, role: Role) -> None:
        """更新既有成员资格的角色（OPERATOR_EMAILS 名单移除后可回收 operator 权限）。"""
        async with self._sessions() as session:
            row = await session.scalar(
                select(WorkspaceMemberRow).where(
                    WorkspaceMemberRow.user_id == uuid.UUID(user_id),
                    WorkspaceMemberRow.workspace_id == uuid.UUID(workspace_id),
                )
            )
            if row is not None and row.role != role.value:
                row.role = role.value
                await session.commit()


class AdminUserRow(typing.TypedDict):
    """管理后台用户行（password_hash 绝不进入该结构）。"""

    id: str
    email: str
    created_at: str | None


class SqlAdminUserRepository:
    """管理后台用户账户查询仓储（password_hash 密码哈希绝不向外暴露）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_for_admin(self) -> tuple[AdminUserRow, ...]:
        async with self._sessions() as session:
            rows = (await session.scalars(select(User).order_by(User.created_at))).all()
            return tuple(
                {
                    "id": str(row.id),
                    "email": row.email,
                    "created_at": str(row.created_at) if row.created_at else None,
                }
                for row in rows
            )
