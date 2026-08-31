"""OpenAI 兼容意图分类适配器检查（ADR 0044：未知/畸形输出不臆造意图）。"""

import json

import httpx2 as httpx

from medicalrag_core.chat.model import ChatRequest, MemoryContext
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_infra.providers.llm import LLMProviderConfig, OpenAICompatClassifier


def _leaves() -> tuple[IntentNode, ...]:
    return (
        IntentNode(
            "disease-info",
            level=IntentLevel.TOPIC,
            kind=IntentKind.KNOWLEDGE,
            name="疾病信息",
            description="疾病基本信息",
            examples=("什么是高血压",),
        ),
        IntentNode(
            "urgent",
            level=IntentLevel.TOPIC,
            kind=IntentKind.KNOWLEDGE,
            name="急症",
            description="急症评估",
        ),
    )


def _request() -> ChatRequest:
    return ChatRequest(
        question="高血压是什么病", conversation_id="c", user_id="u", workspace_id="w"
    )


def _classifier(handler) -> OpenAICompatClassifier:
    return OpenAICompatClassifier(
        LLMProviderConfig(base_url="https://api.example.com", model="m"),
        transport=httpx.MockTransport(handler),
    )


def _respond(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_analyze_parses_candidates_slots_and_rewrite():
    payload = {
        "rewritten_question": "高血压的基本信息是什么",
        "intents": [{"id": "disease-info", "score": 0.9, "slots": {"department": "心内科"}}],
        "guidance": None,
    }

    def handler(request):
        return _respond(json.dumps(payload))

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert analysis.rewritten_question == "高血压的基本信息是什么"
    assert [c.node_id for c in analysis.candidates] == ["disease-info"]
    assert analysis.candidates[0].score == 0.9
    assert analysis.slots["disease-info"] == {"department": "心内科"}


async def test_analyze_preserves_unknown_ids_for_tree_whitelisting():
    payload = {"intents": [{"id": "ghost", "score": 0.9}, {"id": "disease-info", "score": 0.5}]}

    def handler(request):
        return _respond(json.dumps(payload))

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert [c.node_id for c in analysis.candidates] == ["ghost", "disease-info"]


async def test_analyze_malformed_output_returns_empty_candidates():
    def handler(request):
        return _respond("不是JSON")

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert analysis.candidates == ()
    assert analysis.rewritten_question == _request().question


async def test_analyze_http_error_returns_empty_candidates():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert analysis.candidates == ()


async def test_analyze_missing_intents_key_returns_empty():
    def handler(request):
        return _respond("{}")

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert analysis.candidates == ()


async def test_analyze_drops_all_when_any_intent_malformed():
    # pydantic 整包校验：任一意图缺 id → 整包无效（ADR 0044 不臆造意图）。
    payload = {"intents": [{"id": "disease-info", "score": 0.9}, {"score": 0.5}]}

    def handler(request):
        return _respond(json.dumps(payload))

    analysis = await _classifier(handler).analyze(_request(), _leaves(), MemoryContext())
    assert analysis.candidates == ()
