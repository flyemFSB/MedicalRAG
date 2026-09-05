"""Aegra 运行时服务入口模块（aegra.json 配置指向本模块导出函数 `graph`）。

负责在 Aegra 服务启动时执行一次性依赖装配（采用 fail-fast 快速失败策略：
若数据库或 Qdrant 无法连接则立即阻断启动）。
对外导出图构造工厂与请求认证拦截处理器（通过校验会话 Cookie 解析用户身份与工作区）。
"""

from __future__ import annotations

import os
from http.cookies import SimpleCookie

from langgraph.graph.state import CompiledStateGraph
from qdrant_client import QdrantClient

from medicalrag_agent.graph import build_graph
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_infra.chat_pipeline import build_chat_pipeline
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.operator import SqlMembershipRepository
from medicalrag_infra.providers.llm import LLMProviderConfig

# 模块级单例缓存：Aegra 无应用生命周期关闭钩子，进程退出时自然回收；
# 需要优雅关闭/连接池管理时再按 Aegra 生命周期事件接入。
_session_factory = None
_redis_client = None


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _, _session_factory = create_engine_and_session_factory(
            os.environ["MEDICALRAG_DATABASE_URL"]
        )
    return _session_factory


def _get_redis():
    global _redis_client
    if _redis_client is None:
        from redis.asyncio import from_url

        _redis_client = from_url(os.environ.get("MEDICALRAG_REDIS_URL", "redis://localhost:6379/0"))
    return _redis_client


async def _build_pipeline() -> ChatPipeline:
    llm = LLMProviderConfig(
        base_url=os.environ.get("MEDICALRAG_LLM_BASE_URL", "https://api.openai.com"),
        api_key=os.environ.get("MEDICALRAG_LLM_API_KEY") or None,
        model=os.environ.get("MEDICALRAG_LLM_MODEL", "gpt-4o-mini"),
    )
    qdrant = QdrantClient(url=os.environ.get("MEDICALRAG_QDRANT_URL", "http://localhost:6333"))
    return await build_chat_pipeline(
        session_factory=_get_session_factory(),
        qdrant=qdrant,
        llm=llm,
        collection=os.environ.get("MEDICALRAG_QDRANT_COLLECTION") or "medical_chunks_v1",
        embedding_dim=int(os.environ.get("MEDICALRAG_QDRANT_EMBEDDING_DIM", "1536")),
        retrieval_policy=RetrievalPolicy(
            version=int(os.environ.get("MEDICALRAG_RETRIEVAL_POLICY_VERSION", "1")),
            context_cap=int(os.environ.get("MEDICALRAG_RETRIEVAL_CONTEXT_CAP", "8")),
        ),
        redis_url=os.environ.get("MEDICALRAG_REDIS_URL"),
    )


async def graph() -> CompiledStateGraph:
    """零参数异步图工厂（Aegra 启动时 await 一次，完成编译并缓存图实例）。"""
    return build_graph(await _build_pipeline())


async def _workspace_ids(user_id: str) -> list[str]:
    """查询用户成员的工作区（与 FastAPI 侧 UserCtx 解析同源，保障检索隔离语义一致）。"""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        memberships = await SqlMembershipRepository(_get_session_factory()).memberships_of(user_id)
        return list(memberships.workspaces())
    except (
        SQLAlchemyError
    ):  # 工作区解析失败时仅丢隔离上下文，图按不存在的工作区过滤（空召回，安全降级）
        return []


async def authenticate(headers: dict[str, str]) -> dict[str, object]:
    """Aegra 认证处理器（对应 aegra.json 中的 auth.path 配置）：校验客户端请求的会话 Cookie。

    入参 headers 为完整的 HTTP 请求头字典（包含 Cookie）；
    经 Redis 服务端会话仓储解析 user_id，并解析其成员工作区，
    返回 {"identity": user_id, "workspace_ids": [...]} 供 Aegra 框架注入图执行 config。
    若用户未登录或会话已过期则返回空字典（按匿名身份处理）。
    """
    from medicalrag_infra.auth.sessions import RedisSessionStore

    # 安全 Cookie 命名随环境切换（生产 __Host- 前缀，本地普通名）；两者都尝试。
    parsed = SimpleCookie()
    parsed.load(headers.get("Cookie", "") or headers.get("cookie", "") or "")
    morsel = None
    for name in ("__Host-SessionID", "MedicalRAG-SessionID"):
        candidate = parsed.get(name)
        if candidate is not None and candidate.value:
            morsel = candidate
            break
    if morsel is None:
        return {}
    store = RedisSessionStore(_get_redis())
    user_id = await store.load(morsel.value)
    if user_id is None:
        return {}
    return {"identity": user_id, "workspace_ids": await _workspace_ids(user_id)}
