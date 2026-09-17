"""API 组合依赖项：会话鉴权、工作区解析与管理员权限校验。

- ``current_user`` —— 从 HTTP 会话 Cookie 中解析已登录用户身份（纯读操作，不触发写库）；
- ``ensure_workspace`` —— 在用户注册或登录时确保个人工作区与成员资格初始化完成（唯一写点）；
- ``require_operator`` —— 校验当前用户具备平台管理员权限（在 OPERATOR_EMAILS 名单内），方可访问运营管理后台端点。

v1 阶段以「个人工作区」作为多工作区数据隔离载体；工作区创建与角色提权仅在认证事件（register/login）中触发，
普通读请求路径实现零写库：有效杜绝每请求写放大与并发首次登录时的竞态问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from medicalrag_core.identity.workspace import Role, Workspace, WorkspaceMember
from medicalrag_core.ids import uuid7
from medicalrag_infra.persistence.operator import OperatorRepositories

from .settings import session_cookie_name


@dataclass(frozen=True, slots=True)
class UserContext:
    """当前已认证用户的解析上下文实体。"""

    user_id: str
    email: str
    workspace_id: str
    role: Role


async def ensure_workspace(
    repos: OperatorRepositories, user_id: str, email: str, operator_emails: frozenset[str]
) -> tuple[str, Role]:
    """确保用户具备个人工作区与成员资格记录；返回 (workspace_id, role) 元组。

    用户角色依据 OPERATOR_EMAILS 判定：命中即授予 operator 角色（首次注册或角色提权），否则为 member 角色。
    本方法仅在 register 与 login 认证事件中调用（保障读请求路径零写库）。
    """
    memberships = await repos.memberships.memberships_of(user_id)
    desired_role = Role.OPERATOR if email in operator_emails else Role.MEMBER
    if memberships.workspaces():
        workspace_id = memberships.workspaces()[0]
        current = memberships.is_platform_operator()
        if desired_role is Role.OPERATOR and not current:
            # 已是成员：原地提权（INSERT 会撞 uq_workspace_member 唯一约束把登录打成 500）
            await repos.memberships.set_role(user_id, workspace_id, Role.OPERATOR)
        elif desired_role is Role.MEMBER and current:
            # 名单移除即降权：避免邮箱移出 OPERATOR_EMAILS 后 DB 记录仍保留 operator 角色
            await repos.memberships.set_role(user_id, workspace_id, Role.MEMBER)
        return workspace_id, desired_role
    workspace = Workspace(id=str(uuid7()), name=email)
    await repos.workspaces.create(workspace)
    await repos.memberships.add(
        WorkspaceMember(user_id=user_id, workspace_id=workspace.id, role=desired_role)
    )
    return workspace.id, desired_role


async def current_user(request: Request) -> UserContext:
    """提取并校验当前请求的会话 Cookie，解析用户上下文。"""
    settings = request.app.state.settings
    token = request.cookies.get(session_cookie_name(settings.cookie_secure))
    user_id = await request.app.state.sessions.load(token) if token is not None else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")
    user = await request.app.state.users.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    repos: OperatorRepositories = request.app.state.operator
    memberships = await repos.memberships.memberships_of(user_id)
    if not memberships.workspaces():
        # 会话有效但账号未完成工作区初始化：重新登录即可自愈（登录逻辑会自动调用 ensure_workspace）
        raise HTTPException(status_code=403, detail="账号未初始化工作区，请重新登录")
    workspace_id = memberships.workspaces()[0]
    role = Role.OPERATOR if memberships.is_platform_operator() else Role.MEMBER
    return UserContext(user_id=user_id, email=user.email, workspace_id=workspace_id, role=role)


async def require_operator(ctx: Annotated[UserContext, Depends(current_user)]) -> UserContext:
    """要求请求主体必须具备平台管理员（operator）角色；否则抛出 403 Forbidden。"""
    if ctx.role is not Role.OPERATOR:
        raise HTTPException(status_code=403, detail="需要 operator 权限")
    return ctx


UserCtx = Annotated[UserContext, Depends(current_user)]
OperatorCtx = Annotated[UserContext, Depends(require_operator)]
