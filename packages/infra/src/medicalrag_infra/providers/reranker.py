"""外部重排模型（Reranker）适配器（ADR 0037：对粗排候选集执行二次相关性重排）。

实现 medical_core.evidence.rerank.Reranker 协议端口。
调用兼容 OpenAI 规范的 /v1/rerank 端点（契约：POST /rerank，入参包含 model, query, documents；返回各切片相关性得分 relevance_score）。
当外部 Reranker 服务发生故障时抛出 ProviderUnavailableError，上层编排流水线自动兜底采用多路融合的原始通道分数继续执行——
重排器仅用于相关性调序，严禁凭空构造 Evidence 实体，亦不变更既定的安全访问控制策略。
"""

from __future__ import annotations

import httpx2 as httpx  # 全仓自有 HTTP 通信统一采用 httpx2（ADR 0081 供应链基线）

from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.evidence.evidence import Candidate

from .llm import LLMProviderConfig


class OpenAICompatReranker:
    """基于兼容 /rerank 接口的外部重排模型适配器。"""

    def __init__(
        self, config: LLMProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            transport=transport,
            base_url=f"{config.base_url.rstrip('/')}/v1",
            timeout=config.timeout_s,
        )

    async def rerank(self, query: str, candidates: tuple[Candidate, ...]) -> tuple[Candidate, ...]:
        """对传入的候选切片集合执行二次打分并回填 reranker_score。"""
        if not candidates:
            return ()
        documents = [c.snippet for c in candidates]
        try:
            response = await self._client.post(
                "/rerank",
                json={"model": self._config.model, "query": query, "documents": documents},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        results = payload.get("results", [])
        scores = {int(item["index"]): float(item.get("relevance_score", 0.0)) for item in results}
        return tuple(
            Candidate(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                source_id=c.source_id,
                title=c.title,
                snippet=c.snippet,
                intent=c.intent,
                channel=c.channel,
                score=c.score,
                is_eligible=c.is_eligible,
                reranker_score=scores.get(index),
                source_quality=c.source_quality,
            )
            for index, c in enumerate(candidates)
        )
