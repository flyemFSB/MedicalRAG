"""ChatPipeline 单一装配工厂（供 API 服务与 Agent 组合根共享复用，遵循包边界规范）。

将各运行时所需的编排依赖（LLM 配置 → 向量嵌入 Provider → Qdrant 集合初始化 → 检索器 → 存储仓储 / 会话记忆 / 意图树 → ChatPipeline）
收敛至单一标准装配入口，杜绝多处装配导致的行为漂移。
调用方仅需按需注入差异化配置（如 redis_url / reranker / retrieval_policy 等），内部统一依赖装配顺序与默认策略。
各应用的组合根仍专注于自身的生命周期管理与依赖注入，本模块仅封装「如何确定性构造 ChatPipeline 实例」。
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.retrieval.ports import EmbeddingProvider

from .persistence.intent_tree import SqlIntentTreeRepository
from .persistence.memory import SqlMemory
from .persistence.run_repository import SqlRunRepository
from .providers.embeddings import CachedEmbeddingProvider, OpenAICompatEmbeddingProvider
from .providers.llm import LLMProviderConfig, OpenAICompatClassifier, OpenAICompatGenerator
from .providers.reranker import OpenAICompatReranker
from .retrieval.qdrant import QdrantRetriever
from .retrieval.schema import DEFAULT_COLLECTION, DEFAULT_EMBEDDING_DIM, ensure_collection

__all__ = ["build_chat_pipeline"]


async def build_chat_pipeline(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: QdrantClient,
    llm: LLMProviderConfig,
    retrieval_policy: RetrievalPolicy,
    collection: str = DEFAULT_COLLECTION,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    redis_url: str | None = None,
    reranker: bool = False,
) -> ChatPipeline:
    """依据标准装配顺序构造 ChatPipeline 编排实例；差异化配置通过参数显式注入。

    - ``redis_url``：传入时自动启用查询侧向量嵌入缓存（规范 Phase 3 优化）；
    - ``reranker``：为 True 时启用外部重排器；否则融合阶段按各通道检索原始分排序。
    """
    ensure_collection(qdrant, collection, embedding_dim=embedding_dim)
    embeddings: EmbeddingProvider = OpenAICompatEmbeddingProvider(llm)
    if redis_url:
        from redis.asyncio import from_url

        embeddings = CachedEmbeddingProvider(embeddings, from_url(redis_url), namespace=llm.model)
    return ChatPipeline(
        memory=SqlMemory(session_factory),
        classifier=OpenAICompatClassifier(llm),
        retriever=QdrantRetriever(
            qdrant,
            embeddings,
            collection=collection,
        ),
        generator=OpenAICompatGenerator(llm),
        runs=SqlRunRepository(session_factory),
        tree=await SqlIntentTreeRepository(session_factory).load(),
        retrieval_policy=retrieval_policy,
        reranker=OpenAICompatReranker(llm) if reranker else None,
    )
