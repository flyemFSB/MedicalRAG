"""结构感知文档分块（遵循结构优先与尺寸纪律约束）。

分块边界原则：依据标题章节定义 Chunk，并携带完整的 heading_path 溯源路径。
依据尺寸纪律补充规则：
- **tolerance 双阶段预算**：章节在 ``tolerance_tokens`` 内保持原子（「切开语义单元的代价
  高于超出目标尺寸」）；超过 tolerance 才按句子边界切分并携带滑动重叠（Overlap）。
- **表格特殊化**：管道表与 HTML 表按行级切分（行内原子，绝不切断一行），每块内容重复
  表头保证展示完整，但**向量文本只取 KV 正文、不含表头**——表头重复前缀会把同一张表
  各块的向量朝同一方向拉，压低同表不同行的区分度。
Markdown 表格章节视为可切分行序列；Token 计数由调用方注入（medical-core 保持零框架/
分词器依赖；生产环境由 Worker 注入真实 tiktoken 计数）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

_MAX_TOKENS = 500
_OVERLAP_TOKENS = 64  # 约占 500 Token 块大小的 10%–15%
# tolerance：语义单元原子的容忍上限（ragent 同名语义；maxChars×3 封顶的 Token 版）。
# 超过 max_tokens 但在 tolerance 内的章节保持单块，避免句中硬切破坏证据完整性。
_TOLERANCE_TOKENS = 1500
_TABLE_ROWS_PER_CHUNK = 50  # 单个表格块的最大数据行数（行内原子，行数硬上限）

# 中英文句末标点（含英文句号；小数点/缩写偶被误切属可接受代价）与换行
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n.]*[。！？!?；;\n.]+|[^。！？!?；;\n.]+$")

_PIPE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_PIPE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_HTML_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_HTML_CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Section:
    """结构化文档中的单个章节：包含标题层级（从 1 起始）、标题文本及正文内容。"""

    level: int
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    """结构感知的 Chunk 实体：包含分块正文、章节标题路径溯源及所属文档标识。

    ``embedding_text_override`` 供表格块使用：展示正文（content）保留完整表格（含表头），
    向量文本改用 KV 正文（不含表头）；None 表示向量文本即正文本身。
    """

    document_id: str
    text: str
    heading_path: tuple[str, ...]
    index: int
    embedding_text_override: str | None = None


def _default_count(text: str) -> int:
    # 极简兜底估计（中日韩文本估算约为 0.5 Token/字符），生产环境必须传入真实分词计数器
    return max(1, len(text) // 2)


def _sentences(text: str) -> list[str]:
    """按中英文句末标点及换行切分句子，完整保留标点符号。"""
    return [m.group(0) for m in _SENTENCE_RE.finditer(text) if m.group(0).strip()]


def _is_table(text: str) -> bool:
    """判断是否为 Markdown 管道表（多数非空行以 | 开头）。"""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    bars = sum(1 for line in lines if line.lstrip().startswith("|"))
    return bars * 2 >= len(lines)


def _looks_like_html_table(text: str) -> bool:
    """判断是否为 HTML 表格（MinerU 常见产物形态），且至少两个数据行才有切分价值。"""
    return "<table" in text.lower() and len(_HTML_ROW_RE.findall(text)) >= 2


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub("", html).strip()


def _pipe_cells(row: str) -> list[str]:
    """把一行管道表拆为单元格（去首尾空管道，转义还原）。"""
    stripped = row.strip().strip("|")
    return [cell.replace("\\|", "|").strip() for cell in stripped.split("|")]


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _group_rows(
    row_tokens: list[int], *, max_tokens: int, rows_per_chunk: int, header_tokens: int
) -> list[list[int]]:
    """把表格数据行按下标分组：行内原子（单行超预算也整行独立成块，绝不切断一行），
    每块预算需为重复表头预留 ``header_tokens``。"""
    groups: list[list[int]] = []
    current: list[int] = []
    used = header_tokens
    for offset, tokens in enumerate(row_tokens):
        if current and (len(current) >= rows_per_chunk or used + tokens > max_tokens):
            groups.append(current)
            current, used = [], header_tokens
        current.append(offset)
        used += tokens
    # 两个调用方（管道表 / HTML 表）都已挡掉「无数据行」，故循环必执行一次、current 必非空
    groups.append(current)
    return groups


def _split_pipe_table(
    text: str, count_tokens: Callable[[str], int], *, max_tokens: int, rows_per_chunk: int
) -> list[tuple[str, str | None]]:
    """把管道表切为 (展示正文, KV 向量文本) 片段；行内原子、每块重复表头、表头不进向量。"""
    rows = [line for line in text.splitlines() if _PIPE_ROW_RE.match(line)]
    if not rows:
        return [(text, "")]
    header_cells = _pipe_cells(rows[0])
    body_rows = [row for row in rows[1:] if not _PIPE_SEPARATOR_RE.match(row)]
    if not header_cells or not body_rows:
        return [(text, "")]
    separator = "| " + " | ".join(["---"] * len(header_cells)) + " |"
    header_md = "| " + " | ".join(_escape_cell(c) for c in header_cells) + " |"
    header_tokens = count_tokens(header_md)

    kv_lines = [
        "; ".join(
            f"{header_cells[i]}: {cell}"
            for i, cell in enumerate(_pipe_cells(row)[: len(header_cells)])
        )
        for row in body_rows
    ]
    row_tokens = [count_tokens(line) for line in kv_lines]
    groups = _group_rows(
        row_tokens,
        max_tokens=max_tokens,
        rows_per_chunk=rows_per_chunk,
        header_tokens=header_tokens,
    )

    pieces: list[tuple[str, str | None]] = []
    for group in groups:
        content = "\n".join([header_md, separator, *(body_rows[i] for i in group)])
        kv = "\n".join(kv_lines[i] for i in group)
        pieces.append((content, kv))
    return pieces


def _split_html_table(
    text: str, count_tokens: Callable[[str], int], *, max_tokens: int, rows_per_chunk: int
) -> list[tuple[str, str | None]]:
    """把 HTML 表格按 <tr> 切分（剥 colspan/rowspan=1 噪声），每块包回完整 <table> 外壳。

    展示正文保留原始行 HTML（保真），KV 向量文本取单元格纯文本；扫不出数据行则整块原样保留。
    """
    cleaned = re.sub(r"\s*colspan=[\"']?1[\"']?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*rowspan=[\"']?1[\"']?", "", cleaned, flags=re.IGNORECASE)
    row_htmls = [match for match in _HTML_ROW_RE.findall(cleaned) if _HTML_CELL_RE.findall(match)]
    if len(row_htmls) < 2:
        return [(text, "")]
    header_cells = [_strip_tags(c) for c in _HTML_CELL_RE.findall(row_htmls[0])]
    body_htmls = row_htmls[1:]
    header_tokens = count_tokens(row_htmls[0])

    kv_lines = [
        "; ".join(
            f"{header_cells[i]}: {cell}"
            for i, cell in enumerate(
                [_strip_tags(c) for c in _HTML_CELL_RE.findall(row)][: len(header_cells)]
            )
        )
        for row in body_htmls
    ]
    row_tokens = [count_tokens(line) for line in kv_lines]
    groups = _group_rows(
        row_tokens,
        max_tokens=max_tokens,
        rows_per_chunk=rows_per_chunk,
        header_tokens=header_tokens,
    )

    pieces: list[tuple[str, str | None]] = []
    for group in groups:
        # 内容 = 表头行 + 本组数据行（还原完整 <tr> 包裹保真）；KV 文本只含本组数据行
        content = (
            "<table>\n"
            + "\n".join([f"<tr>{row_htmls[0]}</tr>", *(f"<tr>{body_htmls[i]}</tr>" for i in group)])
            + "\n</table>"
        )
        kv = "\n".join(kv_lines[i] for i in group)
        pieces.append((content, kv))
    return pieces


def _split_oversized(
    sentence: str, count_tokens: Callable[[str], int], max_tokens: int
) -> list[str]:
    """当单句超出 Token 上限时按字符比例强制切分（兜底保护措施）。"""
    total = count_tokens(sentence) or len(sentence) or 1  # 计数器返回 0 时退化为按字符等分
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
    # 只有「纯空白章节 + 超大计数值」会得到空 units；公有入口 chunk_document 会过滤空分块，
    # 故此处另一侧无可观察行为，声明为无分支而不是写一个永远无法失败的测试
    if current:  # pragma: no branch
        packed.append(current)
    return ["".join(parts) for parts in packed]


def chunk_document(
    document_id: str,
    sections: Sequence[Section],
    *,
    count_tokens: Callable[[str], int] | None = None,
    max_tokens: int = _MAX_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
    tolerance_tokens: int = _TOLERANCE_TOKENS,
    table_rows_per_chunk: int = _TABLE_ROWS_PER_CHUNK,
) -> tuple[Chunk, ...]:
    """将结构化文档划分为分块：表格按行级切分；普通章节在容忍上限（tolerance）内保持语义完整，超限后按句子切分。

    标题路径依据层级动态维护：新章节会覆盖同级及更深子级，自动重置更浅层级。
    ``tolerance_tokens`` 为语义单元原子的容忍上限（≥ max_tokens，构造时收敛）。
    """
    counter = count_tokens or _default_count
    tolerance = max(tolerance_tokens, max_tokens)
    chunks: list[Chunk] = []
    path: list[str] = []
    for section in sections:
        if section.level < 1:
            # 层级非法会让 heading_path 静默吞掉上一级标题（溯源失真），fail-fast 而非静默走样
            raise ValueError(f"Section 层级必须从 1 起始，收到 {section.level}")
        path = path[: section.level - 1]
        path.append(section.heading)
        if _looks_like_html_table(section.text):
            pieces = _split_html_table(
                section.text, counter, max_tokens=max_tokens, rows_per_chunk=table_rows_per_chunk
            )
        elif _is_table(section.text):
            pieces = _split_pipe_table(
                section.text, counter, max_tokens=max_tokens, rows_per_chunk=table_rows_per_chunk
            )
        elif counter(section.text) <= tolerance:
            pieces: list[tuple[str, str | None]] = [(section.text, None)]
        else:
            pieces = [
                (text, None)
                for text in _pack_with_overlap(
                    _sentences(section.text), counter, max_tokens, overlap_tokens
                )
            ]
        for content, override in pieces:
            if not content.strip():
                continue  # 空章节或空分块不参与嵌入与索引（避免产生低质量召回源）
            chunks.append(
                Chunk(
                    document_id=document_id,
                    text=content,
                    heading_path=tuple(path),
                    index=len(chunks),
                    embedding_text_override=override or None,
                )
            )
    return tuple(chunks)


def embedding_text(chunk: Chunk) -> str:
    """构造用于向量嵌入的文本：章节标题路径 + 正文（表格块用 KV 正文替代完整表格）。

    标题路径携带层级上下文；表格块经 ``embedding_text_override`` 剔除重复表头，
    表身份由章节路径承载而非表头前缀。
    """
    body = chunk.embedding_text_override if chunk.embedding_text_override else chunk.text
    heading = " > ".join(chunk.heading_path)
    return f"{heading}\n{body}" if heading else body
