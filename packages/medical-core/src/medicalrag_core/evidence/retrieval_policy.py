"""版本化检索与融合策略（策略参数由版本化数据驱动）。

将证据融合（Evidence Fusion）的各项配额与排序偏好声明为纯值对象。
策略的变更仅通过产生新的策略版本推进，旧版本保持不可变以供历史审计（spec 可审计性）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """证据融合与证据容量封顶策略配置。

    ``version`` 为单调递增的整数版本号；``context_cap`` 为进入生成上下文的证据数量上限；
    ``channel_quotas`` 限制各检索通道（如 dense、sparse）的最大入选数量；
    ``intent_quota`` 限制同一子意图的最大入选数量；
    ``intent_priority`` 用于决胜排序时的意图优先级权重映射；
    ``intent_min_score`` 为意图候选的置信度下限（0.0 关闭；对齐参考实现 0.35——
    低分意图不进检索，交由澄清引导兜底）；
    ``rerank_candidate_limit`` 为送外部重排器的候选池上限（成本天花板；0 关闭截断）。
    """

    version: int
    context_cap: int
    channel_quotas: Mapping[str, int] = field(default_factory=dict)
    intent_quota: int = 0
    intent_priority: Mapping[str, int] = field(default_factory=dict)
    # 证据闸门（Evidence Gate）：融合后最高分低于该阈值的整批证据一律丢弃（宁可拒答不硬答）；
    # 0.0 表示闸门关闭。阈值语义对齐重排分数范围（0~1），需与 Reranker 输出同尺度。
    evidence_min_score: float = 0.0
    intent_min_score: float = 0.35
    rerank_candidate_limit: int = 40
