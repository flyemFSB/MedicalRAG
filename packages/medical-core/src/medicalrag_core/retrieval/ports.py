"""检索域适配器端口协议。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    """文本向量嵌入适配器端口：将输入文本序列转换为稠密浮点向量。

    向量维度、距离度量方式及归一化规则由不可变的嵌入模式版本（Embedding Schema Version）统一约束；
    本端口协议承诺输出与当前生效 Schema 维度严格匹配的向量集合。
    """

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...
