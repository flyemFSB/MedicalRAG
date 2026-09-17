"""确定性证据融合。

融合流水线按固定 6 步严格执行：
1. 过滤：淘汰未通过发布资格校验（is_eligible=False）的候选；
2. 去重归并：按 chunk_id 分组，合并意图与检索通道来源，选取得分最高的主候选；
3. 优先级排序：按 (派生分数降序, 意图优先级降序, chunk_id 升序) 稳定排序；
4. 通道配额截断：限制各检索通道（channel）的最大入选数量；
5. 意图配额截断：限制各子意图（intent）的最大入选数量；
6. 证据总容量封顶：最终按策略上限截取前 context_cap 项，并赋予稳定引用编号（[1], [2], ...）。
"""

from __future__ import annotations

from collections.abc import Sequence

from .evidence import Candidate, Evidence
from .retrieval_policy import RetrievalPolicy


def _derived_score(candidate: Candidate) -> float:
    """计算用于排序的派生分数：重排器分数存在时优先采用，否则使用检索通道原始分。"""
    return candidate.reranker_score if candidate.reranker_score is not None else candidate.score


def fuse(candidates: Sequence[Candidate], policy: RetrievalPolicy) -> tuple[Evidence, ...]:
    """将多通道检索候选确定性融合为有序、受配额约束且已封顶的证据元组。"""
    # 1. 资格校验：仅允许合格的已发布版本进入后续融合流程
    eligible = [candidate for candidate in candidates if candidate.is_eligible]
    if not eligible:
        return ()

    # 2. 按 chunk_id 去重归并等价候选，将来源并集收敛至派生分数最高的代表候选。
    #    同分时按 (intent, channel) 字典序决胜：Qdrant 服务端 RRF 产出离散分数，同分并不罕见，
    #    代表候选的 intent/channel 决定后续配额归属，必须与输入顺序无关（跨 Run 可复现）。
    by_chunk: dict[str, list[Candidate]] = {}
    for candidate in eligible:
        by_chunk.setdefault(candidate.chunk_id, []).append(candidate)
    merged: list[tuple[Candidate, list[Candidate]]] = [
        (max(group, key=lambda c: (_derived_score(c), c.intent, c.channel)), group)
        for group in by_chunk.values()
    ]

    # 3-4. 依据派生分数、意图优先级排序，最后以 chunk_id 进行确定性决胜
    merged.sort(
        key=lambda pair: (
            -_derived_score(pair[0]),
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
            continue
        if (
            policy.intent_quota
            and intent_counts.get(representative.intent, 0) >= policy.intent_quota
        ):
            continue
        quotaed.append((representative, group))
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        intent_counts[representative.intent] = intent_counts.get(representative.intent, 0) + 1

    # 6. 对最终入选证据集合执行数量封顶，并生成引用序号标签（[1], [2], ...）
    kept = quotaed[: policy.context_cap]
    return tuple(
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
        )
        for index, (representative, group) in enumerate(kept, start=1)
    )
