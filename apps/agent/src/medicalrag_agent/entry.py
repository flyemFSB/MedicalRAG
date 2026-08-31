"""Aegra 运行时服务入口模块（aegra.json 配置指向本模块导出函数 `graph`）。

负责在 Aegra 服务启动时执行一次性依赖装配（采用 fail-fast 快速失败策略：若数据库或 Qdrant 无法连接则立即阻断启动）。
对外导出图构造工厂与请求认证拦截处理器（通过校验会话 Cookie 解析用户身份）。
"""

from __future__ import annotations

import os

from langgraph.graph.state import CompiledStateGraph
from qdrant_client import QdrantClient

from medicalrag_agent.graph import build_graph
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_infra.chat_pipeline import build_chat_pipeline
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.providers.llm import LLMProviderConfig


async def _build_pipeline() -> ChatPipeline:
    database_url = os.environ["MEDICALRAG_DATABASE_URL"]
    llm = LLMProviderConfig(
        base_url=os.environ.get("MEDICALRAG_LLM_BASE_URL", "https://api.openai.com"),
        api_key=os.environ.get("MEDICALRAG_LLM_API_KEY") or None,
        model=os.environ.get("MEDICALRAG_LLM_MODEL", "gpt-4o-mini"),
    )
    _, session_factory = create_engine_and_session_factory(database_url)
    qdrant = QdrantClient(url=os.environ.get("MEDICALRAG_QDRANT_URL", "http://localhost:6333"))
    return await build_chat_pipeline(
        session_factory=session_factory,
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


async def authenticate(headers: dict[str, str]) -> dict[str, object]:
    """Aegra 认证处理器（对应 aegra.json 中的 auth.path 配置）：校验客户端请求的会话 Cookie。

    入参 headers 为完整的 HTTP 请求头字典（包含 Cookie）；
    经由 Redis 服务端会话仓储解析 user_id，并返回 {"identity": {"user_id": ...}} 供 Aegra 框架自动注入 langgraph_auth_user。
    若用户未登录或会话已过期则返回空字典（按匿名身份处理）。
    """
    from redis.asyncio import from_url

    from medicalrag_infra.auth.sessions import RedisSessionStore

    redis_url = os.environ.get("MEDICALRAG_REDIS_URL", "redis://localhost:6379/0")
    cookie_name = (
        "MedicalRAG-SessionID"  # 本地开发环境 Cookie 名；生产环境通过 Nginx 注入 __Host- 前缀
    )
    raw = headers.get("Cookie", "") or headers.get("cookie", "") or ""
    token = None
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == cookie_name:
            token = value
            break
    if token is None:
        return {}
    redis_client = from_url(redis_url)
    try:
        store = RedisSessionStore(redis_client)
        user_id = await store.load(token)
    finally:
        await redis_client.aclose()
    if user_id is None:
        return {}
    return {"identity": {"user_id": user_id}}
