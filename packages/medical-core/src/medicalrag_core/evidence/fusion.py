"""确定性证据融合（ADR 0039）。

融合流水线按固定 6 步严格执行：
1. 过滤：淘汰未通过发布资格校验（is_eligible=False）的候选；
2. 去重归并：按 chunk_id 分组，合并意图与检索通道来源，选取得分最高的主候选；
3. 优先级排序：按 (派生分数降序, 来源质量降序, 意图优先级降序, chunk_id 升序) 稳定排序；
4. 通道配额截断：限制各检索通道（channel）的最大入选数量；
5. 意图配额截断：限制各子意图（intent）的最大入选数量；
6. 上下文总容量封顶：最终截取前 context_cap 项并赋予稳定引用编号（[1], [2], ...）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .evidence import Candidate, DroppedCandidate, Evidence
from .retrieval_policy import RetrievalPolicy


@dataclass(frozen=True, slots=True)
class FusionResult:
    """证据融合输出结果：按最终顺序排列的保留证据列表与被淘汰候选记录。"""

    evidence: tuple[Evidence, ...]
    dropped: tuple[DroppedCandidate, ...]


def _derived_score(candidate: Candidate) -> float:
    """计算用于排序的派生分数：重排器分数存在时优先采用，否则使用检索通道原始分。"""
    return candidate.reranker_score if candidate.reranker_score is not None else candidate.score


def fuse(candidates: Sequence[Candidate], policy: RetrievalPolicy) -> FusionResult:
    """将多通道检索候选确定性融合为有序、受配额约束且已封顶的证据集合。"""
    if not candidates:
        return FusionResult((), ())

    dropped: list[DroppedCandidate] = []

    # 1. 资格校验：仅允许合格的已发布版本进入后续融合流程
    eligible: list[Candidate] = []
    for candidate in candidates:
        if candidate.is_eligible:
            eligible.append(candidate)
        else:
            dropped.append(DroppedCandidate(candidate.chunk_id, "publication_not_eligible"))
    if not eligible:
        return FusionResult((), tuple(dropped))

    # 2. 按 chunk_id 去重归并等价候选，将来源并集收敛至派生分数最高的代表候选
    by_chunk: dict[str, list[Candidate]] = {}
    for candidate in eligible:
        by_chunk.setdefault(candidate.chunk_id, []).append(candidate)
    merged: list[tuple[Candidate, list[Candidate]]] = [
        (max(group, key=_derived_score), group) for group in by_chunk.values()
    ]

    # 3-4. 依据派生分数、来源质量、意图优先级排序，最后以 chunk_id 进行确定性决胜
    merged.sort(
        key=lambda pair: (
            -_derived_score(pair[0]),
            -pair[0].source_quality,
            -policy.intent_priority.get(pair[0].intent, 0),
            pair[0].chunk_id,
        )
    )

    # 5. 按照排序顺序依次执行通道配额与意图配额过滤
    quotaed: list[tuple[Candidate, list[Candidate]]] = []
    channel_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    for representative, group in merged:
        channel = representative.channel
        channel_quota = policy.channel_quotas.get(channel)
        if channel_quota is not None and channel_counts.get(channel, 0) >= channel_quota:
            dropped.append(DroppedCandidate(representative.chunk_id, "channel_quota"))
            continue
        if (
            policy.intent_quota
            and intent_counts.get(representative.intent, 0) >= policy.intent_quota
        ):
            dropped.append(DroppedCandidate(representative.chunk_id, "intent_quota"))
            continue
        quotaed.append((representative, group))
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        intent_counts[representative.intent] = intent_counts.get(representative.intent, 0) + 1

    # 6. 为模型上下文封顶最终证据集合并生成序号引用标签
    kept = quotaed[: policy.context_cap]
    for representative, _ in quotaed[policy.context_cap :]:
        dropped.append(DroppedCandidate(representative.chunk_id, "context_cap"))

    evidence = tuple(
        Evidence(
            source_id=representative.source_id,
            document_id=representative.document_id,
            chunk_id=representative.chunk_id,
            title=representative.title,
            snippet=representative.snippet,
            intent_provenance=frozenset(candidate.intent for candidate in group),
            channel_provenance=frozenset(candidate.channel for candidate in group),
            raw_score=representative.score,
            score=_derived_score(representative),
            citation_label=f"[{index}]",
            policy_version=policy.version,
            retained_reason="retained",
        )
        for index, (representative, group) in enumerate(kept, start=1)
    )
    return FusionResult(evidence, tuple(dropped))
