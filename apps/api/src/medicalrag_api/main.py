"""FastAPI 组合根（遵循最佳实践规范：main 模块仅负责应用实例构造、全局生命周期管理及路由组装）。

生命周期管理负责初始化结构化安全日志、进程级数据库引擎与会话工厂、Redis 客户端、
以及用户身份/会话管理/聊天编排相关依赖；引擎与 Redis 连接在应用停机时自动安全释放。
聊天编排默认依据 Settings 自动装配真实的外部 Provider 适配器；单元/集成测试可传入内存伪实现覆盖。
运营数据面接口统一通过 OperatorRepositories 读写 PostgreSQL 关系库；文档摄取触发则写入事务性 Outbox（ADR 0063）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from qdrant_client import QdrantClient
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.identity.ports import SessionStore
from medicalrag_core.identity.service import IdentityService
from medicalrag_core.identity.sessions import SessionManager
from medicalrag_infra.auth.password import Argon2PasswordHasher
from medicalrag_infra.auth.sessions import InMemorySessionStore, RedisSessionStore
from medicalrag_infra.chat_pipeline import build_chat_pipeline
from medicalrag_infra.logging import configure, logger
from medicalrag_infra.metrics import Metrics
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.intent_tree import SqlIntentTreeRepository
from medicalrag_infra.persistence.operator import OperatorRepositories
from medicalrag_infra.persistence.users import SqlUserRepository
from medicalrag_infra.providers.llm import LLMProviderConfig
from medicalrag_infra.ratelimit import InMemoryRateLimiter, RedisRateLimiter
from medicalrag_infra.storage.local import LocalObjectStorage

from .api.admin import router as admin_router
from .api.auth import router as auth_router
from .api.chat import router as chat_router
from .api.chat_stream import router as chat_stream_router
from .api.conversations import router as conversations_router
from .api.feedback import router as feedback_router
from .api.health import router as health_router
from .api.metrics import router as metrics_router
from .api.upload import router as upload_router
from .settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    session_store: SessionStore | None = None,
    chat_pipeline: ChatPipeline | None = None,
) -> FastAPI:
    """构造并初始化 FastAPI 应用；测试时可传入自定义 Settings、内存 session_store 或自定义 chat_pipeline 覆盖底层适配器。"""
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
            except Exception:  # noqa: BLE001 —— 降级而非崩溃；就绪态探针如实上报 degraded 状态
                await redis_client.aclose()
                effective_redis = None
        app.state.redis_client = effective_redis
        app.state.redis_available = effective_redis is not None
        users = SqlUserRepository(session_factory)
        app.state.identity = IdentityService(users, Argon2PasswordHasher())
        if session_store is not None:
            store = session_store
        elif effective_redis is not None:
            store = RedisSessionStore(effective_redis)
        else:
            store = InMemorySessionStore()
        app.state.sessions = SessionManager(store)
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
        # 聊天流水线执行延迟构造：避免健康检查和认证端点在启动阶段触发远端检索连接
        app.state.chat = chat_pipeline
        app.state.build_chat = lambda: _build_pipeline(resolved, session_factory, qdrant)
        yield
        await engine.dispose()
        if redis_client is not None:
            await redis_client.aclose()

    app = FastAPI(title="MedicalRAG API", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """链路追踪 request_id 拦截中间件：继承上游 X-Request-ID 请求头或自动生成全局唯一 ID；绑定至日志上下文并回写响应头。"""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(chat_stream_router)
    app.include_router(conversations_router)
    app.include_router(feedback_router)
    app.include_router(upload_router)
    app.include_router(admin_router)
    return app


async def _build_pipeline(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: QdrantClient,
) -> ChatPipeline:
    """根据 Settings 配置装配真实聊天编排流水线（装配工厂实现见 infra.chat_pipeline）。"""
    llm = LLMProviderConfig(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or None,
        model=settings.llm_model,
    )
    return await build_chat_pipeline(
        session_factory=session_factory,
        qdrant=qdrant,
        llm=llm,
        collection=settings.qdrant_collection,
        embedding_dim=settings.qdrant_embedding_dim,
        retrieval_policy=RetrievalPolicy(
            version=settings.retrieval_policy_version,
            context_cap=settings.retrieval_context_cap,
        ),
        redis_url=settings.redis_url,
        reranker=bool(settings.rerank_model),
    )
