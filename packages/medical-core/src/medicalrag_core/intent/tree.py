"""动态意图树构建与白名单解析（ADR 0044）。

分类器输出被严格限制为意图树内已启用的叶子节点 ID：对于未知节点或格式错误的分类输出，系统一律不臆造意图。
本模块负责意图树的内存结构组装、环检测与合法性校验、启用叶子目录维护，以及基于「白名单 + 稳定排序 + 阈值过滤 + Top-N 截断」的确定性解析。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .node import IntentNode


class IntentTreeError(ValueError):
    """当意图树结构不合法（如存在重复 ID、父节点不存在、存在环路）时抛出该异常。"""


@dataclass(frozen=True, slots=True)
class ScoredIntent:
    """外部意图分类器输出的单条带置信度分数的意图项。"""

    node_id: str
    score: float


@dataclass(frozen=True, slots=True)
class IntentResolution:
    """意图解析结果：包含白名单命中的有效候选、被剔除的未知节点 ID 列表及对应的意图节点实体。"""

    known: tuple[ScoredIntent, ...]
    unknown: tuple[str, ...]
    nodes: tuple[IntentNode, ...]


class IntentTree:
    """基于节点集合构建的意图树（支持多根森林结构），提供叶子节点索引与确定性白名单解析。"""

    def __init__(self, nodes: Sequence[IntentNode]) -> None:
        self._nodes = {n.id: n for n in nodes}
        if len(self._nodes) != len(nodes):
            raise IntentTreeError("意图节点 ID 存在重复")
        for n in nodes:
            if n.parent_id is not None and n.parent_id not in self._nodes:
                raise IntentTreeError(f"节点 {n.id} 引用的父节点不存在: {n.parent_id}")
        for n in nodes:
            seen: set[str] = set()
            cur = n
            while cur.parent_id is not None:
                if cur.id in seen:
                    raise IntentTreeError(f"意图树存在循环引用环路，涉及节点 {n.id}")
                seen.add(cur.id)
                cur = self._nodes[cur.parent_id]
        self._children: dict[str, list[str]] = {nid: [] for nid in self._nodes}
        for n in nodes:
            if n.parent_id is not None:
                self._children[n.parent_id].append(n.id)
        self._leaves = tuple(n for n in nodes if not self._children[n.id])

    def eligible_leaves(self) -> tuple[IntentNode, ...]:
        """获取所有处于启用状态（enabled）的叶子节点；仅有启用的叶子节点才参与分类匹配。"""
        return tuple(n for n in self._leaves if n.enabled)

    def resolve(
        self,
        candidates: Sequence[ScoredIntent],
        *,
        top_n: int | None = None,
        threshold: float | None = None,
    ) -> IntentResolution:
        """执行白名单确定性解析：剔除未知节点 ID，按置信度分数降序排列（同分按 ID 升序决胜），并应用阈值与 Top-N 截断。

        返回的 ``known`` 仅包含树内已启用的叶子节点 ID；未知的节点 ID 记录于 ``unknown`` 中。
        """
        eligible = frozenset(n.id for n in self.eligible_leaves())
        known: list[ScoredIntent] = []
        unknown: list[str] = []
        for candidate in candidates:
            if candidate.node_id in eligible:
                known.append(candidate)
            else:
                unknown.append(candidate.node_id)
        known.sort(key=lambda c: (-c.score, c.node_id))
        if threshold is not None:
            known = [c for c in known if c.score >= threshold]
        if top_n is not None:
            known = known[:top_n]
        nodes = tuple(self._nodes[c.node_id] for c in known)
        return IntentResolution(tuple(known), tuple(unknown), nodes)
