"""ChatPipeline.run_stream 类型化流式事件检查（ADR 0041 直接流式）。"""

from medicalrag_core.chat.model import Analysis, ChatRequest, MemoryContext, Message, Outcome
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.chat.stream import (
    AnalysisEvent,
    DoneEvent,
    TokenEvent,
)
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentTree, ScoredIntent

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
    """实现 stream 的生成适配器：逐段产出 token。"""

    async def generate(self, context):
        return "整段回答"

    async def stream(self, context):
        for token in ["回答", "流式", "增量"]:
            yield token


class BatchGenerator:
    """仅实现 generate（无 stream）：流式路径应退化为整段一次性产出。"""

    async def generate(self, context):
        return "整段回答"


class FakeRuns:
    async def create_run(self, request) -> str:
        return "run-1"

    async def record_state(self, run_id, state) -> None:
        pass

    async def complete(self, run_id, result) -> None:
        pass


def _pipeline(generator) -> ChatPipeline:
    return ChatPipeline(
        memory=FakeMemory(),
        classifier=FakeClassifier(),
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


async def test_stream_falls_back_to_batch_when_not_streamable():
    pipeline = _pipeline(BatchGenerator())
    events = [event async for event in pipeline.run_stream(_request())]
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    assert [t.text for t in tokens] == ["整段回答"]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.result.message == "整段回答"


async def test_stream_shorts_on_guidance():
    class GuidanceClassifier(FakeClassifier):
        async def analyze(self, request, leaves, context):
            return Analysis(rewritten_question="?", candidates=())

    pipeline = _pipeline(BatchGenerator())
    pipeline._classifier = GuidanceClassifier()
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
