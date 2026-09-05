"""结构感知文档分块（遵循结构优先与尺寸纪律约束）。

分块边界原则：依据标题章节定义 Chunk，并携带完整的 heading_path 溯源路径。
依据尺寸纪律补充规则：
单章节正文超出 Token 上限时，按句子边界切分并携带滑动重叠（Overlap）；Markdown 表格章节视为原子块，严禁拆分。
Token 计数由调用方注入（medical-core 保持零框架/分词器依赖；生产环境由 Worker 注入真实 tiktoken 计数）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

_MAX_TOKENS = 500
_OVERLAP_TOKENS = 64  # 约占 500 Token 块大小的 10%–15%

_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]*[。！？!?；;\n]+|[^。！？!?；;\n]+$")


@dataclass(frozen=True, slots=True)
class Section:
    """结构化文档中的单个章节：包含标题层级（从 1 起始）、标题文本及正文内容。"""

    level: int
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """具备结构感知的 Chunk：包含正文切片、章节标题路径溯源及所属文档标识。"""

    document_id: str
    text: str
    heading_path: tuple[str, ...]
    index: int


def _default_count(text: str) -> int:
    # 极简兜底估计（中日韩文本估算约为 0.5 Token/字符），生产环境必须传入真实分词计数器
    return max(1, len(text) // 2)


def _sentences(text: str) -> list[str]:
    """按中英文句末标点及换行切分句子，完整保留标点符号。"""
    return [m.group(0) for m in _SENTENCE_RE.finditer(text) if m.group(0).strip()]


def _is_table(text: str) -> bool:
    """判断是否为 Markdown 表格（多数非空行以 | 开头）：表格保持原子性，不可拆分。"""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    bars = sum(1 for line in lines if line.lstrip().startswith("|"))
    return bars * 2 >= len(lines)


def _split_oversized(
    sentence: str, count_tokens: Callable[[str], int], max_tokens: int
) -> list[str]:
    """当单句超出 Token 上限时按字符比例强制切分（兜底保护措施）。"""
    total = count_tokens(sentence)
    step = max(1, (len(sentence) * max_tokens) // total)
    return [sentence[i : i + step] for i in range(0, len(sentence), step)]


def _pack_with_overlap(
    sentences: list[str],
    count_tokens: Callable[[str], int],
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """贪心打包生成不超过 max_tokens 的块；相邻块通过共享尾部句子实现重叠（Overlap）。"""
    units: list[str] = []
    for sentence in sentences:
        if count_tokens(sentence) > max_tokens:
            units.extend(_split_oversized(sentence, count_tokens, max_tokens))
        else:
            units.append(sentence)

    packed: list[list[str]] = []
    current: list[str] = []
    used = 0
    carry = 0  # current 头部继承自上一块的重叠句子数量；不足一个新句子时不触发切块
    for unit in units:
        size = count_tokens(unit)
        if len(current) > carry and used + size > max_tokens:
            packed.append(current)
            tail: list[str] = []
            tail_tokens = 0
            for prev in reversed(current):
                prev_size = count_tokens(prev)
                if tail_tokens + prev_size > overlap_tokens:
                    break
                tail.insert(0, prev)
                tail_tokens += prev_size
            # 确保尾部重叠句子与当前句子总长度不超过 max_tokens；装不下则从最早的重叠句依次丢弃
            while tail and tail_tokens + size > max_tokens:
                tail_tokens -= count_tokens(tail.pop(0))
            current = tail
            used = tail_tokens
            carry = len(tail)
        current.append(unit)
        used += size
    if current:
        packed.append(current)
    return ["".join(parts) for parts in packed]


def chunk_document(
    document_id: str,
    sections: Sequence[Section],
    *,
    count_tokens: Callable[[str], int] | None = None,
    max_tokens: int = _MAX_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
) -> tuple[Chunk, ...]:
    """对结构化文档进行分块：普通章节正文独立成块；超长章节在句子边界切分并保留重叠。

    标题路径依据层级动态维护：新章节会覆盖同级及更深子级，自动重置更浅层级。表格章节整表原子保留。
    """
    counter = count_tokens or _default_count
    chunks: list[Chunk] = []
    path: list[str] = []
    for section in sections:
        path = path[: section.level - 1]
        path.append(section.heading)
        if _is_table(section.text) or counter(section.text) <= max_tokens:
            texts: list[str] = [section.text]
        else:
            texts = _pack_with_overlap(
                _sentences(section.text), counter, max_tokens, overlap_tokens
            )
        for text in texts:
            chunks.append(
                Chunk(
                    document_id=document_id,
                    text=text,
                    heading_path=tuple(path),
                    index=len(chunks),
                )
            )
    return tuple(chunks)


def embedding_text(chunk: Chunk) -> str:
    """构造用于向量嵌入的文本：章节标题路径 + 正文（嵌入文本必须携带层级上下文）。"""
    heading = " > ".join(chunk.heading_path)
    return f"{heading}\n{chunk.text}" if heading else chunk.text
