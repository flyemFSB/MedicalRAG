"""Chunk 背景补写适配器端口（enriching 阶段，可选特性）。

为每个 Chunk 生成一段背景说明（阐明其在整篇文档中的上下文位置与核心主题），
同一份补写文本将同时注入稠密（dense）向量嵌入文本与稀疏（sparse）索引文本中。
当补写失败或提供商不可用时，系统自动降级为空背景，不臆造内容且不阻断后续摄取流程。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Contextualizer(Protocol):
    """Chunk 背景补写适配器端口：按文档原始顺序逐 Chunk 生成背景（便于复用提供商 Prompt 缓存）。"""

    async def situate(
        self,
        *,
        document_title: str,
        heading_path: Sequence[str],
        chunk_text: str,
        preceding_text: str,
    ) -> str: ...
