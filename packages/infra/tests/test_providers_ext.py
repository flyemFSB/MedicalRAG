"""Reranker / MinerU Provider 适配器检查（httpx MockTransport 确定性测试）。"""

import httpx2 as httpx
import pytest

from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_infra.providers.llm import LLMProviderConfig
from medicalrag_infra.providers.mineru import MinerUClient, MinerUConfig
from medicalrag_infra.providers.reranker import OpenAICompatReranker


def _candidate(index: int, snippet: str = "片段") -> Candidate:
    return Candidate(
        chunk_id=f"chunk-{index}",
        document_id="doc-1",
        source_id="src-1",
        title="t",
        snippet=snippet,
        intent="disease-info",
        channel="dense",
        score=float(index),
    )


async def test_reranker_attaches_scores_and_preserves_order():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"query"' in body
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 1, "relevance_score": 0.3},
                ]
            },
        )

    reranker = OpenAICompatReranker(
        LLMProviderConfig(base_url="https://example.com", model="rerank-2"),
        transport=httpx.MockTransport(handler),
    )
    candidates = (_candidate(0), _candidate(1))
    result = await reranker.rerank("高血压", candidates)
    assert result[0].reranker_score == 0.9
    assert result[1].reranker_score == 0.3
    assert result[0].chunk_id == "chunk-0"


async def test_reranker_provider_failure_raises():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    reranker = OpenAICompatReranker(
        LLMProviderConfig(base_url="https://example.com", model="rerank-2"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError):
        await reranker.rerank("高血压", (_candidate(0),))


async def test_mineru_request_file_upload_returns_batch_and_url():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v4/file-urls/batch"
        return httpx.Response(
            200, json={"batch_id": "batch-1", "file_urls": ["https://cdn.example.com/put"]}
        )

    client = MinerUClient(
        MinerUConfig(base_url="https://mineru.example.com", token="secret"),
        transport=httpx.MockTransport(handler),
    )
    batch_id, upload_url = await client.request_file_upload("doc.pdf")
    assert batch_id == "batch-1"
    assert upload_url == "https://cdn.example.com/put"
