"""索引质量与发布门禁校验（validating 阶段；发布门禁）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexValidation:
    """索引校验结果：包含是否通过的布尔标识及未通过时的审计原因列表。"""

    passed: bool
    reasons: tuple[str, ...]


def validate_index(
    *,
    expected_chunks: int,
    indexed_chunks: int,
    checksum_ok: bool,
    active_schema: bool,
) -> IndexValidation:
    """对真实索引状态执行多维校验；全部检查项均通过才允许转入 published 发布态（发布门禁）。"""
    failures: list[str] = []
    if indexed_chunks != expected_chunks:
        failures.append(
            f"Chunk 数量不一致: 索引点数 {indexed_chunks} != 期望块数 {expected_chunks}"
        )
    if not checksum_ok:
        failures.append("内容哈希校验不匹配")
    if not active_schema:
        failures.append("向量维度与生效的嵌入 Schema 不匹配")
    return IndexValidation(passed=not failures, reasons=tuple(failures))
