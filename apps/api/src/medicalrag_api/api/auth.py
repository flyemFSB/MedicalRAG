"""用户认证与会话管理 API 路由（包含注册、登录、登出及当前用户信息查询；服务端会话与安全 Cookie 规范）。

安全防御机制：
- 用户注册与登录成功后均重新生成会话令牌（有效防御会话固定攻击）；
- 密码仅通过 Argon2id 哈希算法校验；认证失败时返回统一的错误提示，不暴露邮箱是否存在（防用户枚举）；
- Cookie 安全属性：HttpOnly 杜绝 XSS 读取、Secure 保障仅在 HTTPS 链路传输、SameSite=Strict 防范 CSRF 跨站请求伪造；
- 个人工作区初始化与管理员角色升级仅绑定在认证事件触发（保障日常读请求零写库）；
- 登录接口基于来源客户端 IP 执行速率限制，防范暴力破解攻击。
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from medicalrag_core.identity.ports import SessionStore
from medicalrag_core.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidCredentialsError,
)
from medicalrag_core.identity.workspace import Role

from ..deps import UserCtx, ensure_workspace
from ..settings import session_cookie_name

router = APIRouter(prefix="/api/auth")

# 会话 TTL：令牌仅作服务端索引键，不携带业务载荷
_SESSION_TTL_S = 86400


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: Role


def _client_ip(request: Request) -> str:
    """提取客户端真实 IP 地址：优先获取 Nginx 反向代理注入的 X-Real-IP；直连时回退至 Socket 连接地址。

    信任边界假设（发布面前必须复核）：X-Real-IP 仅可信于「所有外部流量都经 nginx 覆写该头」的拓扑
    （compose 中 api 只绑定 127.0.0.1 且 nginx 全部 api location 均用 $remote_addr 覆写）；
    若 api 直接对外暴露，该头可被伪造，登录防爆破将被绕过——届时必须改用 socket 地址或可信代理链。
    """
    return request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )


def _set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=session_cookie_name(secure),
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _session_token(request: Request) -> str | None:
    return request.cookies.get(session_cookie_name(request.app.state.settings.cookie_secure))


async def _throttle_login(request: Request) -> None:
    settings = request.app.state.settings
    allowed = await request.app.state.rate_limiter.acquire(
        f"auth:{_client_ip(request)}",
        limit=settings.auth_rate_limit,
        window_s=settings.auth_rate_window_s,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="尝试过于频繁，请稍后再试")


async def _issue_session(store: SessionStore, user_id: str) -> str:
    """签发新会话令牌（登录/注册后强制换新，防会话固定）。"""
    token = secrets.token_urlsafe(32)
    await store.save(token, user_id, ttl_s=_SESSION_TTL_S)
    return token


@router.post("/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response) -> UserOut:
    """新用户注册：校验唯一性、创建账号、初始化个人工作区并设置会话 Cookie。"""
    # 注册与登录共用同一 IP 限流桶：防止开放注册被批量刷号
    await _throttle_login(request)
    identity: IdentityService = request.app.state.identity
    store: SessionStore = request.app.state.sessions
    try:
        user_id = await identity.register(body.email, body.password)
    except DuplicateUserError as err:
        raise HTTPException(status_code=409, detail="该邮箱已注册") from err
    _, role = await ensure_workspace(
        request.app.state.operator,
        user_id,
        body.email.lower(),
        request.app.state.settings.operator_email_set,
    )
    token = await _issue_session(store, user_id)
    _set_session_cookie(response, token, secure=request.app.state.settings.cookie_secure)
    return UserOut(id=user_id, email=body.email, role=role)


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response) -> UserOut:
    """用户登录认证：IP 限流校验、Argon2 密码校验、确保工作区就绪并签发新会话 Cookie。"""
    await _throttle_login(request)
    identity: IdentityService = request.app.state.identity
    store: SessionStore = request.app.state.sessions
    try:
        user_id = await identity.authenticate(body.email, body.password)
    except InvalidCredentialsError as err:
        raise HTTPException(status_code=401, detail="邮箱或密码错误") from err
    _, role = await ensure_workspace(
        request.app.state.operator,
        user_id,
        body.email.lower(),
        request.app.state.settings.operator_email_set,
    )
    token = await _issue_session(store, user_id)
    _set_session_cookie(response, token, secure=request.app.state.settings.cookie_secure)
    return UserOut(id=user_id, email=body.email, role=role)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """用户退出登录：服务端撤销会话令牌并清除客户端 Cookie。"""
    token = _session_token(request)
    if token is not None:
        await request.app.state.sessions.delete(token)
    response.delete_cookie(session_cookie_name(request.app.state.settings.cookie_secure), path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(ctx: UserCtx) -> UserOut:
    """获取当前已登录用户的基本信息（含角色，供前端权限门禁与 Topbar 条件渲染）。

    复用 deps.current_user 依赖：token→validate→get_user→工作区校验与 deps 同源，消除重复。
    """
    return UserOut(id=ctx.user_id, email=ctx.email, role=ctx.role)
