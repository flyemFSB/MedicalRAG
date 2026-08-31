"""版本化检索与融合策略（ADR 0038：策略参数由版本化数据驱动）。

将证据融合（Evidence Fusion）的各项配额与排序偏好声明为纯值对象。
策略的变更仅通过产生新的策略版本推进，旧版本保持不可变以供历史审计（spec 可审计性）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """证据融合与上下文封顶策略配置。

    ``version`` 为单调递增的整数版本号（ADR 0038）；``context_cap`` 为进入模型上下文的证据项上限；
    ``channel_quotas`` 限制各检索通道（如 dense、sparse）的最大入选数量；
    ``intent_quota`` 限制同一子意图的最大入选数量；
    ``intent_priority`` 用于决胜排序时的意图优先级权重映射。
    """

    version: int
    context_cap: int
    channel_quotas: Mapping[str, int] = field(default_factory=dict)
    intent_quota: int = 0
    intent_priority: Mapping[str, int] = field(default_factory=dict)
