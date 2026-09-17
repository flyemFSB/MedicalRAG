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


async def test_prompt_groups_evidence_by_document_and_omits_titles():
    """ADR 0087：证据按文档分组渲染且 prompt 不含文档标题（标题只进前端证据面板）。"""
    from dataclasses import replace

    titled = replace(_evidence(), title="高血压防治指南（2024）")
    other_doc = replace(_evidence(), chunk_id="chunk-2", document_id="doc-2", citation_label="[2]")
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    await _generator(handler).generate(replace(_context(), evidence=(titled, other_doc)))
    system = captured["body"]["messages"][0]["content"]
    assert "文档 doc-1：" in system
    assert "文档 doc-2：" in system
    assert "高血压防治指南（2024）" not in system  # 标题不进 prompt
    assert "[1] 高血压的常规管理包括低盐饮食。" in system


async def test_history_strips_citation_markers():
    """ADR 0087：助手历史消息进入生成上下文前剥离 [n] 角标（不留作下一轮噪声）。"""
    from dataclasses import replace

    from medicalrag_core.chat.model import MemoryContext, Message, MessageRole

    memory = MemoryContext(
        messages=(
            Message(role=MessageRole.USER, text="高血压要注意什么？"),
            Message(role=MessageRole.ASSISTANT, text="需要注意低盐饮食 [1]。"),
        )
    )
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    await _generator(handler).generate(replace(_context(), memory=memory))
    contents = [m["content"] for m in captured["body"]["messages"][1:]]
    assert "需要注意低盐饮食。" in contents
    assert not any("[1]" in c for c in contents)


def _chunk(content: str) -> str:
    payload = {
        "id": "cmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def test_stream_yields_content_deltas_until_done():
    sse = _chunk("高") + _chunk("血压") + "data: [DONE]\n\n"

    def handler(request):
        # SDK 的 .stream() 辅助器依赖 SSE content-type 才能解析事件流
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

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
