"""稀疏（BM25）通道的文本预处理与模型构造。

索引端与查询端必须共用本模块，保证稀疏向量对称一致。

为什么需要预处理：fastembed 的 `Qdrant/bm25` 使用 SimpleTokenizer（`[^\\w]` → 空格后按空白切分），
且默认按英文做词干化与停用词过滤。中文没有词间空格，整句会被切成「标点之间的长串」——
单个 token 往往十几个汉字，超过 `token_max_length=40` 还会被直接丢弃，
于是查询词与文档 token 几乎不可能相等，中文稀疏通道基本失效。

处理方式：CJK 段按 **bigram** 切分（无词典分词的标准做法，Lucene CJKAnalyzer 同思路），
ASCII/数字保持原样；同时关闭英文词干与停用词（英文词干对中文词元只会造成破坏）。
"""

from __future__ import annotations

import re

from fastembed import SparseTextEmbedding

from .schema import DEFAULT_SPARSE_MODEL

_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_PIECE_RE = re.compile(rf"[{_CJK}]+|[0-9a-z][0-9a-z._-]*")
_CJK_RE = re.compile(rf"^[{_CJK}]+$")


def bm25_text(text: str) -> str:
    """把输入文本转换为 BM25 词元串（CJK 用 bigram，其余按词）。"""
    tokens: list[str] = []
    for piece in _PIECE_RE.findall(text.lower()):
        if not _CJK_RE.match(piece):
            tokens.append(piece)
            continue
        if len(piece) == 1:
            tokens.append(piece)
        else:
            tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
    return " ".join(tokens)


def build_sparse_model(model_name: str = DEFAULT_SPARSE_MODEL) -> SparseTextEmbedding:
    """构造静态 BM25 模型：关闭英文词干提取与停用词过滤（面向中文医学文本，避免英文预处理削弱召回）。"""
    return SparseTextEmbedding(model_name, disable_stemmer=True)


__all__ = ["bm25_text", "build_sparse_model"]
