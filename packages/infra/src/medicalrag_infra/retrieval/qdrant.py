"""Qdrant 混合检索适配器（实现 medical_core.chat.ports.Retriever 协议端口；ADR 0012 / ADR 0026 / ADR 0039 迁移至 Qdrant）。

依托 Qdrant 原生支持的 dense + sparse 双路混合检索（Hybrid Search）与 RRF（Reciprocal Rank Fusion，k=60）倒数排名融合算法：
通过 prefetch API 同时发起稠密向量与稀疏向量检索，由 Qdrant 引擎在服务端直接完成 RRF 融合打分。
稀疏向量由 fastembed 的 SparseTextEmbedding（静态 Qdrant/bm25 模型）在运行时对查询文本对称生成（无状态模型，保证索引与检索两端严格对称）。
"""

from __future__ import annotations

import asyncio

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from medicalrag_core.chat.model import ChatRequest, IntentQuery
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.retrieval.ports import EmbeddingProvider

from .schema import DEFAULT_COLLECTION, DEFAULT_SPARSE_MODEL

_RRF_K = 60


class QdrantRetriever:
    """基于 Qdrant prefetch + RRF 融合的混合检索适配器。

    在线检索时采用 fastembed 静态 BM25 模型对查询文本提取稀疏向量（无状态、与索引端对称）。
    """

    def __init__(
        self,
        client: QdrantClient,
        embeddings: EmbeddingProvider,
        *,
        collection: str = DEFAULT_COLLECTION,
        limit: int = 50,
        sparse_model: SparseTextEmbedding | None = None,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._collection = collection
        # 宽召回默认配置（规范 Phase 1）：每路检索 50 条送入 RRF，最终由证据融合（Evidence Fusion）层执行配额与截断
        self._limit = limit
        self._sparse_model = sparse_model or SparseTextEmbedding(DEFAULT_SPARSE_MODEL)

    def _query_text(self, query: IntentQuery) -> str:
        # ADR 0036：检索查询主体为模型重写后的用户问题，后附槽位中提取的医学实体（Medical Entity）；
        # 意图节点的名称与描述仅在缺失重写问题时作为兜底，不再作为默认检索主体。
        parts: list[str] = []
        if query.rewritten_question:
            parts.append(query.rewritten_question)
        parts.extend(str(value) for value in query.slots.values())
        if not parts:
            parts.append(query.node.name)
            if query.node.description:
                parts.append(query.node.description)
        return " ".join(parts)

    def _build_filter(self, workspace_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=workspace_id),
                ),
                models.FieldCondition(
                    key="is_eligible",
                    match=models.MatchValue(value=True),
                ),
            ],
        )

    async def _text_to_sparse(self, text: str) -> models.SparseVector:
        emb = next(iter(await asyncio.to_thread(lambda: self._sparse_model.embed([text]))))
        return models.SparseVector(
            indices=list(emb.indices),
            values=list(emb.values),
        )

    async def retrieve(
        self, request: ChatRequest, queries: tuple[IntentQuery, ...]
    ) -> tuple[Candidate, ...]:
        query_filter = self._build_filter(request.workspace_id)

        # 文本去重后并发执行各路意图检索（规范 Phase 1：多意图并行执行，不串行等待）
        seen_texts: set[str] = set()
        unique: list[tuple[str, IntentQuery]] = []
        for query in queries:
            text = self._query_text(query)
            if text in seen_texts:
                continue
            seen_texts.add(text)
            unique.append((text, query))
        if not unique:
            return ()

        groups = await asyncio.gather(
            *(self._retrieve_one(text, query, query_filter) for text, query in unique)
        )
        return tuple(candidate for group in groups for candidate in group)

    async def _retrieve_one(
        self,
        text: str,
        query: IntentQuery,
        query_filter: models.Filter,
    ) -> list[Candidate]:
        vectors = await self._embeddings.embed([text])
        dense_vector = vectors[0]
        sparse_vector = await self._text_to_sparse(text)

        # Qdrant 服务端原生双路混合检索：dense + sparse 双路 prefetch → RRF 融合
        prefetches = [
            models.Prefetch(
                query=list(dense_vector),
                using="dense_vec",
                limit=self._limit,
            ),
            models.Prefetch(
                query=sparse_vector,
                using="sparse_vec",
                limit=self._limit,
            ),
        ]

        result = await asyncio.to_thread(
            self._client.query_points,
            collection_name=self._collection,
            prefetch=prefetches,
            query=models.RrfQuery(
                rrf=models.Rrf(k=_RRF_K),
            ),
            query_filter=query_filter,
            limit=self._limit,
            with_payload=True,
        )

        candidates: list[Candidate] = []
        for point in result.points:
            payload = point.payload or {}
            candidates.append(
                Candidate(
                    chunk_id=str(payload.get("chunk_id", "")),
                    document_id=str(payload.get("document_id", "")),
                    source_id=str(payload.get("source_id", "")),
                    title=str(payload.get("title", "")),
                    snippet=str(payload.get("snippet", "")),
                    intent=query.node.id,
                    channel="hybrid",
                    score=point.score,
                    is_eligible=True,
                )
            )
        return candidates
