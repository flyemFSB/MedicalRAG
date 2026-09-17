"""FastAPI 组合根（遵循最佳实践规范：main 模块仅负责应用实例构造、全局生命周期管理及路由组装）。

生命周期管理负责初始化结构化安全日志、进程级数据库引擎与会话工厂、Redis 客户端、
以及用户身份/会话管理相关依赖；引擎与 Redis 连接在应用停机时自动安全释放。
运营数据面接口统一通过 OperatorRepositories 读写 PostgreSQL 关系库；文档摄取触发则写入事务性 Outbox。
生产聊天经由 Aegra Agent Protocol v2 运行时（apps/agent）消费，本服务不装配聊天编排流水线。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from redis.asyncio import Redis, from_url

from medicalrag_core.identity.ports import SessionStore
from medicalrag_core.identity.service import IdentityService
from medicalrag_infra.auth.password import Argon2PasswordHasher
from medicalrag_infra.auth.sessions import InMemorySessionStore, RedisSessionStore
from medicalrag_infra.logging import configure, logger
from medicalrag_infra.metrics import Metrics
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.intent_tree import SqlIntentTreeRepository
from medicalrag_infra.persistence.operator import OperatorRepositories
from medicalrag_infra.persistence.users import SqlUserRepository
from medicalrag_infra.ratelimit import InMemoryRateLimiter, RedisRateLimiter
from medicalrag_infra.storage.local import LocalObjectStorage

from .api.admin import router as admin_router
from .api.auth import router as auth_router
from .api.conversations import router as conversations_router
from .api.feedback import router as feedback_router
from .api.health import router as health_router
from .api.metrics import router as metrics_router
from .api.samples import router as samples_router
from .api.upload import router as upload_router
from .settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    session_store: SessionStore | None = None,
) -> FastAPI:
    """构造并初始化 FastAPI 应用；测试时可传入自定义 Settings 或内存 session_store 覆盖底层适配器。"""
    resolved = settings or Settings()  # type: ignore[reportCallIssue]  # 配置通过环境变量注入
    engine, session_factory = create_engine_and_session_factory(resolved.database_url)
    redis_client: Redis | None = None if session_store is not None else from_url(resolved.redis_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure(level=resolved.log_level.upper())
        app.state.settings = resolved
        app.state.session_factory = session_factory
        # 当 Redis 不可用时自动降级回退至进程内会话仓储与限流器（架构规范「本地优雅降级 + degraded 状态指示」）
        effective_redis: Redis | None = redis_client
        if redis_client is not None:
            try:
                await redis_client.ping()
            except Exception:
                await redis_client.aclose()
                effective_redis = None
        app.state.redis_client = effective_redis
        app.state.redis_available = effective_redis is not None
        users = SqlUserRepository(session_factory)
        app.state.identity = IdentityService(users, Argon2PasswordHasher())
        app.state.users = users
        if session_store is not None:
            store = session_store
        elif effective_redis is not None:
            store = RedisSessionStore(effective_redis)
        else:
            store = InMemorySessionStore()
        app.state.sessions = store
        app.state.operator = OperatorRepositories(session_factory)
        app.state.intent_tree_repo = SqlIntentTreeRepository(session_factory)
        app.state.object_storage = LocalObjectStorage(resolved.object_root)
        app.state.metrics = Metrics()
        app.state.rate_limiter = (
            RedisRateLimiter(effective_redis)
            if effective_redis is not None
            else InMemoryRateLimiter()
        )
        qdrant = QdrantClient(url=resolved.qdrant_url)
        app.state.qdrant_client = qdrant
        yield
        # 停机回收（规范 §1.4）：Qdrant → Redis → 引擎；单个失败不阻断其余清理
        with suppress(Exception):
            await asyncio.to_thread(qdrant.close)
        if redis_client is not None:
            with suppress(Exception):
                await redis_client.aclose()
        await engine.dispose()

    app = FastAPI(title="MedicalRAG API", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """链路追踪 request_id 拦截中间件：继承上游 X-Request-ID 请求头或自动生成全局唯一 ID；绑定至日志上下文并回写响应头。"""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        # 同时暂存于 request.state：未处理异常处理器位于中间件栈之外，无法复用 contextualize 上下文
        request.state.request_id = request_id
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """未处理异常统一收敛：带 request_id 的结构化日志（可观测承诺在 500 场景不断链）+ 不泄漏堆栈的 500 响应。"""
        request_id = getattr(request.state, "request_id", None) or "-"
        logger.bind(request_id=request_id).exception(
            "捕获未处理异常（服务内部错误）：request_path={}", request.url.path
        )
        return JSONResponse(status_code=500, content={"detail": "内部服务器错误"})

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(feedback_router)
    app.include_router(samples_router)
    app.include_router(upload_router)
    app.include_router(admin_router)
    return app
