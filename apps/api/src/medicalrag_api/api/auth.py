"""用户认证与会话管理 API 路由（包含注册、登录、登出及当前用户信息查询；服务端会话与安全 Cookie 规范）。

安全防御机制：
- 用户注册与登录成功后均重新生成会话令牌（有效防御会话固定攻击）；
- 密码仅通过 Argon2id 哈希算法校验；认证失败时返回统一的错误提示，不暴露邮箱是否存在（防用户枚举）；
- Cookie 安全属性：HttpOnly 杜绝 XSS 读取、Secure 保障仅在 HTTPS 链路传输、SameSite=Strict 防范 CSRF 跨站请求伪造；
- 个人工作区初始化与管理员角色升级仅绑定在认证事件触发（保障日常读请求零写库）；
- 登录接口基于来源客户端 IP 执行速率限制，防范暴力破解攻击。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from medicalrag_core.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidCredentialsError,
)
from medicalrag_core.identity.sessions import SessionManager

from ..deps import ensure_workspace
from ..settings import session_cookie_name

router = APIRouter(prefix="/api/auth")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: EmailStr


def _client_ip(request: Request) -> str:
    """提取客户端真实 IP 地址：优先获取 Nginx 反向代理注入的 X-Real-IP；直连时回退至 Socket 连接地址。"""
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


@router.post("/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response) -> UserOut:
    """新用户注册：校验唯一性、创建账号、初始化个人工作区并设置会话 Cookie。"""
    identity: IdentityService = request.app.state.identity
    sessions: SessionManager = request.app.state.sessions
    try:
        user_id = await identity.register(body.email, body.password)
    except DuplicateUserError:
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    await ensure_workspace(
        request.app.state.operator,
        user_id,
        body.email.lower(),
        request.app.state.settings.operator_email_set,
    )
    token = await sessions.create(user_id)
    _set_session_cookie(response, token, secure=request.app.state.settings.cookie_secure)
    return UserOut(id=user_id, email=body.email)


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response) -> UserOut:
    """用户登录认证：IP 限流校验、Argon2 密码校验、确保工作区就绪并签发新会话 Cookie。"""
    await _throttle_login(request)
    identity: IdentityService = request.app.state.identity
    sessions: SessionManager = request.app.state.sessions
    try:
        user_id = await identity.authenticate(body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    await ensure_workspace(
        request.app.state.operator,
        user_id,
        body.email.lower(),
        request.app.state.settings.operator_email_set,
    )
    token = await sessions.create(user_id)
    _set_session_cookie(response, token, secure=request.app.state.settings.cookie_secure)
    return UserOut(id=user_id, email=body.email)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """用户退出登录：服务端撤销会话令牌并清除客户端 Cookie。"""
    token = _session_token(request)
    if token is not None:
        await request.app.state.sessions.revoke(token)
    response.delete_cookie(session_cookie_name(request.app.state.settings.cookie_secure), path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request) -> UserOut:
    """获取当前已登录用户的基本信息。"""
    token = _session_token(request)
    user_id = await request.app.state.sessions.validate(token) if token is not None else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")
    user = await request.app.state.identity.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return UserOut(id=user.id, email=user.email)
