"""Token 计数工具模块（基于 cl100k_base 编码，精确匹配 OpenAI 及主流模型的分词标准）。

用于摄取阶段的 Chunk 分块大小预算与成本度量；tiktoken 分词编码器采用进程内单例缓存，离线安全可用。
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """基于 cl100k_base 编码精确计算给定文本的 Token 数量。"""
    return len(_encoding().encode(text))
