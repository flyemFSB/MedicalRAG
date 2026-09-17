"""工作区（Workspace）隔离域（规范定义：Workspace / Workspace Member）。

Workspace 为多成员共享知识库（Knowledge Base）、会话（Conversation）与运营审计记录的逻辑隔离边界；
User 可隶属于多个 Workspace。角色决定权限边界：普通成员（member）仅可访问其所属 Workspace 的内部资源，
操作员（operator）则享有平台级的管理运营权限。领域层提供确定性权限判定逻辑与持久化端口。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol


class Role(enum.StrEnum):
    """工作区内的用户角色（规范定义：MEMBER 与 OPERATOR）。"""

    MEMBER = "member"
    OPERATOR = "operator"


@dataclass(frozen=True, slots=True)
class Workspace:
    """成员共享知识库与会话资源的逻辑隔离空间。"""

    id: str
    name: str
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """用户在指定工作区中的成员资格与对应角色。"""

    user_id: str
    workspace_id: str
    role: Role


@dataclass(frozen=True, slots=True)
class UserMemberships:
    """用户所属的全部工作区成员资格集合（角色判定依据最大授权原则）。"""

    user_id: str
    memberships: tuple[WorkspaceMember, ...]

    def workspaces(self) -> tuple[str, ...]:
        return tuple(sorted({m.workspace_id for m in self.memberships}))

    def is_platform_operator(self) -> bool:
        return any(m.role is Role.OPERATOR for m in self.memberships)


class WorkspaceRepository(Protocol):
    """工作区持久化操作端口。"""

    async def create(self, workspace: Workspace) -> None: ...


class MembershipRepository(Protocol):
    """工作区成员资格持久化端口。"""

    async def add(self, member: WorkspaceMember) -> None: ...
    async def memberships_of(self, user_id: str) -> UserMemberships: ...
