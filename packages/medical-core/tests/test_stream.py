"""ChatPipeline.run_stream 类型化流式事件检查（ADR 0041 直接流式）。"""

from medicalrag_core.chat.model import (
    Analysis,
    ChatRequest,
    ChatResult,
    MemoryContext,
    Message,
    Outcome,
)
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.chat.stream import (
    AnalysisEvent,
    DoneEvent,
    EvidenceEvent,
    SafetyEvent,
    TokenEvent,
)
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.fusion import fuse
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentTree, ScoredIntent
from medicalrag_core.safety.policy import RiskClass, assess

_TREE = IntentTree(
    [
        IntentNode("medical", level=IntentLevel.DOMAIN, kind=IntentKind.KNOWLEDGE, name="医学"),
        IntentNode(
            "disease-info",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="疾病信息",
        ),
    ]
)


class FakeMemory:
    async def load(self, request):
        return MemoryContext()

    async def append(self, request, message: Message) -> None:
        pass


class FakeClassifier:
    async def analyze(self, request, leaves, context):
        return Analysis(
            rewritten_question=request.question,
            candidates=(ScoredIntent("disease-info", 0.9),),
        )


class FakeRetriever:
    async def retrieve(self, request, queries):
        return (
            Candidate(
                chunk_id="c1",
                document_id="d1",
                source_id="s1",
                title="t",
                snippet="血压 ≥140/90 mmHg",
                intent="disease-info",
                channel="dense",
                score=0.9,
            ),
        )


class StreamingGenerator:
    """流式生成适配器：逐段产出 token。"""

    async def stream(self, context):
        for token in ["回答", "流式", "增量"]:
            yield token


class FakeRuns:
    async def create_run(self, request) -> str:
        return "run-1"

    async def record_state(self, run_id, state) -> None:
        pass

    async def complete(self, run_id, result) -> None:
        pass


def _pipeline(generator, classifier=None) -> ChatPipeline:
    return ChatPipeline(
        memory=FakeMemory(),
        classifier=classifier or FakeClassifier(),
        retriever=FakeRetriever(),
        generator=generator,
        runs=FakeRuns(),
        tree=_TREE,
        retrieval_policy=RetrievalPolicy(version=1, context_cap=4),
    )


async def test_stream_emits_typed_events_in_order():
    pipeline = _pipeline(StreamingGenerator())
    events = [event async for event in pipeline.run_stream(_request())]
    kinds = [type(event).__name__ for event in events]
    assert kinds == [
        "AnalysisEvent",
        "EvidenceEvent",
        "SafetyEvent",
        "TokenEvent",
        "TokenEvent",
        "TokenEvent",
        "DoneEvent",
    ]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.result.outcome is Outcome.ANSWERED
    assert done.result.message == "回答流式增量"


async def test_stream_shorts_on_guidance():
    class GuidanceClassifier(FakeClassifier):
        async def analyze(self, request, leaves, context):
            return Analysis(rewritten_question="?", candidates=())

    pipeline = _pipeline(StreamingGenerator(), GuidanceClassifier())
    events = [event async for event in pipeline.run_stream(_request())]
    assert isinstance(events[0], AnalysisEvent)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].result.outcome is Outcome.GUIDANCE


def _request() -> ChatRequest:
    return ChatRequest(
        question="高血压注意事项",
        conversation_id="conv-1",
        user_id="u-1",
        workspace_id="ws-1",
    )


def test_event_payloads_are_the_sse_serialization_contract():
    """ADR 0080 决策 6：to_payload 是 SSE 端点与 agent graph 共用的唯一序列化出口。

    键名与键集合就是前后端契约：增删字段必须同步改消费方，本测试就是那道闸。
    """
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
        sub_questions=("并发症",),
        guidance_message="需要澄清",
    )
    assert AnalysisEvent(analysis=analysis).to_payload() == {
        "rewritten_question": "高血压注意事项",
        "sub_questions": ["并发症"],
        "intents": [{"node_id": "disease-info", "score": 0.9}],
        "guidance": "需要澄清",
    }

    evidence = fuse(
        (
            Candidate(
                chunk_id="c1",
                document_id="d1",
                source_id="s1",
                title="指南标题",
                snippet="血压 ≥140/90 mmHg",
                intent="disease-info",
                channel="dense",
                score=0.9,
            ),
        ),
        RetrievalPolicy(version=1, context_cap=4),
    )
    assert EvidenceEvent(evidence=evidence).to_payload() == {
        "evidence": [
            {
                "chunk_id": "c1",
                "source_id": "s1",
                "title": "指南标题",
                "snippet": "血压 ≥140/90 mmHg",
                "citation_label": "[1]",
                "score": 0.9,
            }
        ]
    }

    safety = assess(RiskClass.TREATMENT)
    assert SafetyEvent(safety=safety).to_payload() == {
        "risk_class": safety.risk_class.value,
        "scope_notice": safety.scope_notice,
        "escalation": safety.escalation,
    }
    assert TokenEvent(text="增量").to_payload() == {"text": "增量"}

    done = DoneEvent(
        result=ChatResult(
            outcome=Outcome.ANSWERED,
            message="回答",
            run_id="run-1",
            safety=safety,
            message_id="msg-1",
        )
    ).to_payload()
    assert set(done) == {
        "outcome",
        "message",
        "run_id",
        "message_id",
        "evidence",
        "safety_notice",
        "safety_escalation",
    }
    assert done["outcome"] == "answered"
    assert done["evidence"] == []
    assert done["safety_notice"] == safety.scope_notice
    assert done["safety_escalation"] == safety.escalation

    # 无安全评估的终止路径（如空召回）不得因 None 而漏键或抛错
    bare = DoneEvent(
        result=ChatResult(outcome=Outcome.EMPTY, message="无证据", run_id="run-2")
    ).to_payload()
    assert bare["safety_notice"] is None
    assert bare["safety_escalation"] is None
