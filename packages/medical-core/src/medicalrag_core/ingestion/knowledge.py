"""知识库（Knowledge Base）与文档（Document）领域实体（规范定义：用户作用域内的医疗来源集合）。

知识库（Knowledge Base）为工作区用户拥有的来源集合边界；文档（Document）为提交至知识库的原始医疗资料，
包含标题、格式、内容哈希、溯源信息与摄取状态。
领域层仅定义实体及其持久化端口契约；摄取执行的具体 9 阶段状态机见 state_machine，异步驱动逻辑见 Worker 应用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol  # DocumentRepository 用 Protocol 定义契约

from .state_machine import IngestionRunState

# v1 允许接入的文件来源格式白名单（富媒体 Multimodal 格式由 MinerU 处理；Markdown 与纯文本走原生极简解析）。
SUPPORTED_SOURCE_FORMATS = frozenset(
    {".docx", ".pptx", ".xlsx", ".pdf", ".md", ".txt", ".png", ".jpg", ".jpeg"}
)


class UnsupportedSourceFormatError(ValueError):
    """当上传的文件格式不在允许清单内时抛出该异常。"""


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """工作区内的医疗知识库实体。"""

    id: str
    workspace_id: str
    name: str
    description: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """提交至知识库的原始文档实体，包含摄取生命周期状态与检索发布资格。"""

    id: str
    knowledge_base_id: str
    workspace_id: str
    title: str
    format: str
    size_bytes: int
    ingestion_state: IngestionRunState
    chunk_count: int = 0
    published: bool = False
    created_at: str | None = None


def validate_source_format(filename: str) -> str:
    """校验文件名后缀是否符合允许清单，返回规范化的小写扩展名（带前导点）；若不受支持则抛出 UnsupportedSourceFormatError。"""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = f".{suffix}"
    if ext not in SUPPORTED_SOURCE_FORMATS:
        raise UnsupportedSourceFormatError(ext)
    return ext


class DocumentRepository(Protocol):
    """文档持久化端口。"""

    async def create(self, document: Document) -> Document: ...
    async def get(self, document_id: str) -> Document | None: ...
    async def list_for_knowledge_base(self, kb_id: str) -> tuple[Document, ...]: ...
    async def update_state(self, document_id: str, state: IngestionRunState) -> None: ...

    # --- 文档生命周期与发布状态管理---
    async def set_published(self, document_id: str, published: bool) -> None: ...
    async def set_chunk_count(self, document_id: str, count: int) -> None:
        """回写文档分块总数（发布阶段调用）。"""
        ...

    async def delete(self, document_id: str) -> None: ...
    async def list_ids(self) -> tuple[str, ...]: ...
