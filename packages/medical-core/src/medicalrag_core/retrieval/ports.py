"""检索域适配器端口协议。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..chunking.chunking import Chunk


class EmbeddingProvider(Protocol):
    """文本向量嵌入适配器端口：将输入文本序列转换为稠密浮点向量。

    向量维度、距离度量方式及归一化规则由不可变的嵌入模式版本（Embedding Schema Version）统一约束；
    本端口协议承诺输出与当前生效 Schema 维度严格匹配的向量集合。
    """

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class VectorIndexer(Protocol):
    """向量索引操作端口（摄取 indexing / validating 阶段；由 infra 的 QdrantIndexer 实现）。

    ``dense_vectors`` 由 embedding 阶段预先计算，避免索引阶段重复嵌入；
    validating 阶段通过 count/read/dim 在发布前对线上索引做门禁验收。
    """

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
    ) -> None: ...

    async def count_points(self, document_id: str) -> int: ...

    async def read_point_snippets(self, document_id: str, limit: int = 8) -> tuple[str, ...]: ...

    async def dense_dim(self) -> int | None: ...

    async def set_eligibility(self, document_id: str, eligible: bool) -> None: ...
