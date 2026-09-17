"""ChatPipeline 装配工厂（Agent 组合根内部模块；ADR 0060 deletion test：API 已不再装配聊天，
单一消费者不配拥有独立 seam，故自 packages/assembly 收敛至此）。

将编排依赖（LLM 配置 → 向量嵌入 Provider → Qdrant 集合初始化 → 检索器 → 存储仓储 / 会话记忆 /
意图树 → ChatPipeline）收敛至单一装配入口。

生产级能力接线：
- 模型路由：RoutingGenerator / RoutingClassifier 按 model_targets 优先级多候选切换，
  三态熔断状态持久化，流式首包超时自动切换候选；
- 会话记忆摘要：溢出窗口的早期消息后台增量压缩；
- 意图树热更新：TTL 缓存加载器；
- 查询词映射消费：命中的术语意图作为满分候选并入分类结果。

Aegra 无 shutdown 钩子（entry 模块注释）：装配产物不携带 aclose 所有权清单。
"""

from __future__ import annotations

import asyncio
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.retrieval.ports import EmbeddingProvider
from medicalrag_infra.persistence.intent_tree import SqlIntentTreeRepository, TtlIntentTreeLoader
from medicalrag_infra.persistence.memory import SqlMemory
from medicalrag_infra.persistence.ops_repos import (
    SqlModelTargetRepository,
    SqlTermIntentResolver,
)
from medicalrag_infra.persistence.run_repository import SqlRunRepository
from medicalrag_infra.providers.embeddings import (
    CachedEmbeddingProvider,
    OpenAICompatEmbeddingProvider,
)
from medicalrag_infra.providers.llm import (
    LLMProviderConfig,
    OpenAICompatSummarizer,
)
from medicalrag_infra.providers.reranker import OpenAICompatReranker
from medicalrag_infra.providers.routing import ModelRouter, RoutingClassifier, RoutingGenerator
from medicalrag_infra.retrieval.qdrant import QdrantRetriever
from medicalrag_infra.retrieval.schema import ensure_collection

__all__ = ["build_chat_pipeline"]


async def build_chat_pipeline(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: QdrantClient,
    llm: LLMProviderConfig,
    retrieval_policy: RetrievalPolicy,
    collection: str,
    embedding_dim: int,
    embedding_model: str,
    redis: Any | None = None,
    reranker: bool = False,
    first_packet_timeout_s: float = 30.0,
) -> ChatPipeline:
    """依据标准装配顺序构造 ChatPipeline。

    - ``embedding_model``：嵌入模型名（调用方给出具体值，可与 ``llm.model`` 相同）。
    - ``redis``：调用方自有的 Redis 客户端，启用查询侧向量嵌入缓存。
    - ``reranker``：为 True 时启用外部重排器。
    """
    await asyncio.to_thread(ensure_collection, qdrant, collection, embedding_dim=embedding_dim)
    embedding_llm = LLMProviderConfig(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=embedding_model,
        timeout_s=llm.timeout_s,
    )
    embeddings: EmbeddingProvider = OpenAICompatEmbeddingProvider(embedding_llm)
    if redis is not None:
        embeddings = CachedEmbeddingProvider(embeddings, redis, namespace=embedding_model)
    router = ModelRouter(SqlModelTargetRepository(session_factory), llm)
    tree_repo = SqlIntentTreeRepository(session_factory)
    summarizer = OpenAICompatSummarizer(llm)
    generator = RoutingGenerator(router, first_packet_timeout_s=first_packet_timeout_s)
    classifier = RoutingClassifier(router)
    reranker_adapter = OpenAICompatReranker(llm) if reranker else None
    return ChatPipeline(
        memory=SqlMemory(session_factory, summarizer=summarizer),
        classifier=classifier,
        retriever=QdrantRetriever(qdrant, embeddings, collection=collection),
        generator=generator,
        runs=SqlRunRepository(session_factory),
        tree=await tree_repo.load(),
        retrieval_policy=retrieval_policy,
        reranker=reranker_adapter,
        term_intents=SqlTermIntentResolver(session_factory),
        tree_loader=TtlIntentTreeLoader(tree_repo),
    )
