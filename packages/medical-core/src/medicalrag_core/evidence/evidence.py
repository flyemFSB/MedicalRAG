"""证据域实体：定义进入证据融合的候选对象及最终生成的引用项（Evidence）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candidate:
    """进入证据融合阶段的单条检索 Chunk 候选。

    ``channel`` 为产出该候选的检索通道名称（如 "dense" 稠密向量或 "sparse" 稀疏向量）；
    ``intent`` 为驱动该次检索的子意图。``score`` 为 Qdrant 组合排序得分。
    若存在 ``reranker_score``，则代表外部重排器（Reranker Provider）产出的单调归一化得分 [0, 1]，
    在融合排序时享有优先权重。
    """

    chunk_id: str
    document_id: str
    source_id: str
    title: str
    snippet: str
    intent: str
    channel: str
    score: float
    is_eligible: bool = True
    reranker_score: float | None = None
    source_quality: int = 0


@dataclass(frozen=True, slots=True)
class Evidence:
    """经确定性融合后、可注入模型上下文的最终引用项。

    ``intent_provenance`` 与 ``channel_provenance`` 记录融合时合并的所有等价候选的意图与通道并集。
    ``raw_score`` 为代表候选在 Qdrant/检索通道的原始得分；``score`` 为用于最终排序的单调派生得分
    （存在重排分数时取重排分数）；规定每个保留证据均须同时保留原始分与派生分以供审计。
    ``retained_reason`` 记录该项被保留的具体规则原因。
    """

    source_id: str
    document_id: str
    chunk_id: str
    title: str
    snippet: str
    intent_provenance: frozenset[str]
    channel_provenance: frozenset[str]
    raw_score: float
    score: float
    citation_label: str
    policy_version: int
    retained_reason: str

    def to_payload(self) -> dict[str, object]:
        """可引用证据的对外数据载荷（SSE 端点与 Agent Graph 共享统一出口）。"""
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "title": self.title,
            "snippet": self.snippet,
            "citation_label": self.citation_label,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class DroppedCandidate:
    """在证据融合过程中被淘汰的候选，携带明确的可审计淘汰原因。"""

    chunk_id: str
    reason: str
