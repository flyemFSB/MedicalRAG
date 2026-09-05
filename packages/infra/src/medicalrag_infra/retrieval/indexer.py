"""Qdrant 向量索引适配器（摄取管线 indexing 阶段：upsert 文档切片的向量与元数据）。

dense_vec 稠密向量由外部 Embedding Provider 计算；
sparse_vec 稀疏向量由 fastembed 的 SparseTextEmbedding（采用静态 Qdrant/bm25 模型）预先计算并存入索引——
此举为官方推荐最佳实践：无语料库状态依赖，确保索引与检索阶段的对称一致性。
切片正文与元数据写入 payload 供检索阶段引用和溯源校验。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import cast

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from medicalrag_core.chunking.chunking import Chunk, embedding_text
from medicalrag_core.retrieval.ports import EmbeddingProvider

from .schema import DEFAULT_COLLECTION, DEFAULT_SPARSE_MODEL


class QdrantIndexer:
    """负责将文档 Chunk 计算向量嵌入并 upsert 写入 Qdrant 集合。

    chunk_id 采用 {document_id}:{index} 确定性命名规则（供检索阶段去重与溯源引用）；
    dense_vec 由 Embedding Provider 填充；sparse_vec 由 fastembed 静态 BM25 模型计算；
    source_id 与 title 作为文档级来源元数据随摄取作业一并传入。
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
        self._sparse_model = sparse_model or SparseTextEmbedding(DEFAULT_SPARSE_MODEL)

    def _sparse_vec(self, text: str) -> models.SparseVector:
        emb = next(iter(self._sparse_model.embed([text])))
        return models.SparseVector(
            indices=list(emb.indices),
            values=list(emb.values),
        )

    async def index(
        self,
        document_id: str,
        workspace_id: str,
        chunks: Sequence[Chunk],
        *,
        title: str,
        source_id: str,
        dense_vectors: Sequence[Sequence[float]] | None = None,
        embedding_texts: Sequence[str] | None = None,
    ) -> None:
        # 当提供 embedding_texts 时（背景补写），dense 与 sparse 统一共用同一份富文本
        texts = (
            list(embedding_texts)
            if embedding_texts is not None
            else [embedding_text(chunk) for chunk in chunks]
        )
        if dense_vectors is None:
            vectors = await self._embeddings.embed(texts)
        else:
            vectors = list(dense_vectors)
        sparse_vecs = await asyncio.to_thread(lambda: [self._sparse_vec(text) for text in texts])

        points = [
            models.PointStruct(
                id=f"{document_id}:{chunk.index}",
                # VectorStruct 结构由集合模式保证
                vector=cast(
                    "models.VectorStruct",
                    {
                        "dense_vec": list(vector),
                        "sparse_vec": sparse_vec,
                    },
                ),
                payload={
                    "chunk_id": f"{document_id}:{chunk.index}",
                    "document_id": document_id,
                    "source_id": source_id,
                    "title": title,
                    "text": text,
                    "snippet": chunk.text,
                    "workspace_id": workspace_id,
                    # 仅在进入 published 状态后才激活资格，发布前不可被检索
                    "is_eligible": False,
                },
            )
            for chunk, text, vector, sparse_vec in zip(chunks, texts, vectors, sparse_vecs)
        ]

        await asyncio.to_thread(
            self._client.upsert,
            collection_name=self._collection,
            points=points,
        )

    async def count_points(self, document_id: str) -> int:
        """统计指定文档在 Qdrant 索引中的实际向量点数（用于 validating 阶段发布门禁校验）。"""
        result = await asyncio.to_thread(
            self._client.count,
            collection_name=self._collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            ),
            exact=True,
        )
        return int(result.count)

    async def read_point_snippets(self, document_id: str, limit: int = 8) -> tuple[str, ...]:
        """抽样回读向量点的 payload snippet（正文原文，供校验和比对与完整性验收）。"""
        points, _ = await asyncio.to_thread(
            self._client.scroll,
            collection_name=self._collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return tuple(str(p.payload.get("snippet", "")) for p in points if p.payload)

    async def dense_dim(self) -> int | None:
        """读取指定集合的稠密向量维度；若集合不存在或不可达则返回 None。"""
        try:
            info = await asyncio.to_thread(self._client.get_collection, self._collection)
        except Exception:  # noqa: BLE001 —— 缺失或网络异常统一按 Schema 未就绪处理
            return None
        vectors = info.config.params.vectors
        dense = vectors.get("dense_vec") if isinstance(vectors, dict) else None
        return int(dense.size) if dense is not None else None

    # --- 文档生命周期管理---

    def _document_filter(self, document_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
            ]
        )

    async def set_eligibility(self, document_id: str, eligible: bool) -> None:
        """切换指定文档所有向量点的检索可见资格（用于下架/重新发布；向量数据保留在索引中）。"""
        await asyncio.to_thread(
            self._client.set_payload,
            collection_name=self._collection,
            payload={"is_eligible": eligible},
            # 注意：set_payload 的过滤参数名为 points
            points=self._document_filter(document_id),
        )

    async def delete_document(self, document_id: str) -> int:
        """根据 document_id 级联删除该文档的所有向量点，并返回删除前的点数。"""
        count = await self.count_points(document_id)
        await asyncio.to_thread(
            self._client.delete,
            collection_name=self._collection,
            points_selector=self._document_filter(document_id),
        )
        return count

    async def all_document_ids(self) -> set[str]:
        """滚动遍历收集索引中出现的全部 document_id 集合（供孤儿数据对账与清理使用）。"""
        ids: set[str] = set()
        offset = None
        while True:
            points, offset = await asyncio.to_thread(
                self._client.scroll,
                collection_name=self._collection,
                scroll_filter=None,
                limit=256,
                offset=offset,
                with_payload=["document_id"],
                with_vectors=False,
            )
            for point in points:
                if point.payload and point.payload.get("document_id"):
                    ids.add(str(point.payload["document_id"]))
            if offset is None:
                return ids
