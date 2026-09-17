"""Qdrant 混合检索适配器（实现 medical_core.chat.ports.Retriever 协议端口）。

依托 Qdrant 原生支持的 dense + sparse 双路混合检索（Hybrid Search）与 RRF 倒数秩融合算法
（k=61 ≡ Cormack et al. 论文的 1/(rank+60)：Qdrant 名次从 0 起算，故加 1 才是论文语义；
可用构造参数覆盖以便在标注集上扫描调优）：
通过 prefetch API 同时发起稠密向量与稀疏向量检索，由 Qdrant 引擎在服务端直接完成 RRF 融合打分。
稀疏向量由 fastembed 的静态 Qdrant/bm25 模型在运行时对查询文本对称生成（经 `sparse.bm25_text` 中文 bigram 预处理后无状态）。
"""

from __future__ import annotations

import asyncio

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from medicalrag_core.chat.model import ChatRequest, IntentQuery
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.retrieval.ports import EmbeddingProvider

from .schema import DEFAULT_COLLECTION
from .sparse import bm25_text, build_sparse_model

# RRF 常数：61 等价论文 1/(rank+60)（Qdrant 名次从 0 开始）；官方建议在标注集上扫描 {2,5,20,61}
_DEFAULT_RRF_K = 61
# 宽召回默认配置（规范 Phase 1）：每路检索 50 条送入 RRF，最终由证据融合层执行配额与截断
_DEFAULT_LIMIT = 50


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
        sparse_model: SparseTextEmbedding | None = None,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._collection = collection
        self._limit = _DEFAULT_LIMIT
        self._sparse_model = sparse_model or build_sparse_model()
        self._rrf_k = _DEFAULT_RRF_K

    def _query_text(self, query: IntentQuery) -> str:
        # 检索查询主体为模型重写后的用户问题；
        # 意图节点的名称与描述仅在缺失重写问题时作为兜底，不再作为默认检索主体。
        parts: list[str] = []
        if query.rewritten_question:
            parts.append(query.rewritten_question)
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
        prepared = bm25_text(text)
        emb = next(iter(await asyncio.to_thread(lambda: self._sparse_model.embed([prepared]))))
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
                rrf=models.Rrf(k=self._rrf_k),
            ),
            query_filter=query_filter,
            limit=self._limit,
            # payload 白名单：text（≈500 token 的富文本）在检索链路上无读取方，不回传可省一半带宽
            with_payload=["chunk_id", "document_id", "source_id", "title", "snippet"],
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
