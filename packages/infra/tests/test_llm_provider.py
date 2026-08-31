"""OpenAI 兼容生成适配器检查（MockTransport 确定性测试）。"""

import json

import httpx2 as httpx
import pytest

from medicalrag_core.chat.model import GenerationContext, MemoryContext
from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.evidence.evidence import Evidence
from medicalrag_core.safety.policy import RiskClass, assess
from medicalrag_infra.providers.llm import LLMProviderConfig, OpenAICompatGenerator


def _evidence() -> Evidence:
    return Evidence(
        source_id="src-1",
        document_id="doc-1",
        chunk_id="chunk-1",
        title="t",
        snippet="高血压的常规管理包括低盐饮食。",
        intent_provenance=frozenset({"disease-info"}),
        channel_provenance=frozenset({"dense"}),
        raw_score=0.9,
        score=0.9,
        citation_label="[1]",
        policy_version=1,
        retained_reason="retained",
    )


def _context() -> GenerationContext:
    return GenerationContext(
        question="高血压应该注意什么？",
        rewritten_question="高血压日常注意事项",
        evidence=(_evidence(),),
        memory=MemoryContext(),
        safety=assess(RiskClass.TREATMENT),
    )


def _generator(handler) -> OpenAICompatGenerator:
    return OpenAICompatGenerator(
        LLMProviderConfig(base_url="https://api.example.com", api_key="sk-test", model="m"),
        transport=httpx.MockTransport(handler),
    )


async def test_generate_returns_content():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "低盐饮食。"}}]})

    assert await _generator(handler).generate(_context()) == "低盐饮食。"


async def test_generate_raises_provider_error_on_http_failure():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ProviderUnavailableError):
        await _generator(handler).generate(_context())


async def test_generate_raises_provider_error_on_malformed_response():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(ProviderUnavailableError):
        await _generator(handler).generate(_context())


async def test_request_sends_evidence_and_auth_header():
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    await _generator(handler).generate(_context())
    system = captured["body"]["messages"][0]
    assert system["role"] == "system"
    assert "低盐饮食" in system["content"]
    assert captured["body"]["messages"][1]["content"] == "高血压日常注意事项"
    assert captured["auth"] == "Bearer sk-test"


async def test_stream_yields_content_deltas_until_done():
    sse = (
        'data: {"choices":[{"delta":{"content":"高"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"血压"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse)

    chunks: list[str] = []
    async for chunk in _generator(handler).stream(_context()):
        chunks.append(chunk)
    assert chunks == ["高", "血压"]


async def test_stream_raises_provider_error_on_http_failure():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ProviderUnavailableError):
        async for _ in _generator(handler).stream(_context()):
            pass
