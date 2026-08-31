"""Chunk 持久化实体与仓储端口（规范定义：结构感知、可独立索引与溯源引用的文本块）。

Chunk 记录携带完整的来源元数据（所属文档、层级标题链、页面/区域引用）、内容哈希及分词计数；
实际的稠密（dense）与稀疏（sparse）向量由 Qdrant 统一管理（ADR 0075）。领域层仅定义实体与操作协议。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """已持久化落库的单个 Chunk 元数据与正文记录。"""

    id: str
    document_id: str
    workspace_id: str
    text: str
    headings: tuple[str, ...]
    index: int
    checksum: str
    token_count: int = 0
    page_ref: str | None = None
    created_at: str | None = None


class ChunkRepository(Protocol):
    """Chunk 数据访问与持久化端口。"""

    async def insert_many(self, chunks: tuple[ChunkRecord, ...]) -> None: ...
    async def list_for_document(self, document_id: str) -> tuple[ChunkRecord, ...]: ...
    async def count_for_document(self, document_id: str) -> int: ...
