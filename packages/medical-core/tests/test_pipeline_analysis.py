"""Analysis Depth 与外部 Reranker 的流水线接线检查（ADR 0069/0037）。"""

from medicalrag_core.chat.model import Analysis, ChatRequest, MemoryContext, Message
from medicalrag_core.chat.pipeline import ChatPipeline
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


def _request(**overrides) -> ChatRequest:
    defaults = {
        "question": "高血压注意事项",
        "conversation_id": "conv-1",
        "user_id": "u-1",
        "workspace_id": "ws-1",
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


def _candidate(chunk_id: str, score: float) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id="doc-1",
        source_id="src-1",
        title="t",
        snippet="s",
        intent="disease-info",
        channel="dense",
        score=score,
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
        return (_candidate("c1", 0.9), _candidate("c2", 0.5), _candidate("c3", 0.3))


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def rerank(self, query, candidates):
        self.calls.append((query, candidates))
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
                reranker_score=round(c.score * 2, 3),
            )
            for c in candidates
        )


class FakeGenerator:
    def __init__(self) -> None:
        self.calls: list = []

    async def generate(self, context):
        self.calls.append(context)
        return "回答"


class FakeRuns:
    async def create_run(self, request) -> str:
        return "run-1"

    async def record_state(self, run_id, state) -> None:
        pass

    async def complete(self, run_id, result) -> None:
        pass


def _pipeline(*, context_cap: int = 2, reranker=None):
    generator = FakeGenerator()
    pipeline = ChatPipeline(
        memory=FakeMemory(),
        classifier=FakeClassifier(),
        retriever=FakeRetriever(),
        generator=generator,
        runs=FakeRuns(),
        tree=_TREE,
        retrieval_policy=RetrievalPolicy(version=1, context_cap=context_cap),
        reranker=reranker,
    )
    return pipeline, generator


async def test_analysis_depth_raises_evidence_cap():
    pipeline, _ = _pipeline(context_cap=2)
    shallow = await pipeline.run(_request())
    assert len(shallow.evidence) == 2  # 默认封顶
    deep = await pipeline.run(_request(analysis_depth=True))
    assert len(deep.evidence) == 3  # 深度分析：封顶翻倍后全部保留


async def test_analysis_depth_marks_generation_context():
    pipeline, generator = _pipeline(context_cap=10)
    await pipeline.run(_request(analysis_depth=True))
    assert generator.calls[0].analysis is True


async def test_reranker_is_invoked_and_score_used_for_ordering():
    reranker = FakeReranker()
    pipeline, _ = _pipeline(context_cap=10, reranker=reranker)
    result = await pipeline.run(_request())
    assert len(reranker.calls) == 1
    assert reranker.calls[0][0] == "高血压注意事项"
    # 排序分取 reranker 单调分数（0.9*2=1.8）—— 最高者排第一
    assert result.evidence[0].score == round(0.9 * 2, 3)
