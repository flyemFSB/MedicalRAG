"""外部重排适配器端口（ADR 0037 / ADR 0039：对候选集执行二次相关性重排）。

重排器协议契约：接收脱敏查询与候选集合，为候选附加单调归一化的 [0, 1] 重排得分（reranker_score），
供后续证据融合（Evidence Fusion）阶段优先作为排序依据。
重排器仅影响融合排序的派生得分，绝不修改候选的原始文本、ID 或元数据。
"""

from __future__ import annotations

from typing import Protocol

from .evidence import Candidate


class Reranker(Protocol):
    """外部重排模型适配器端口协议。

    接收脱敏查询与候选列表，返回附带单调归一化 reranker_score 的候选元组。
    """

    async def rerank(
        self, query: str, candidates: tuple[Candidate, ...]
    ) -> tuple[Candidate, ...]: ...
