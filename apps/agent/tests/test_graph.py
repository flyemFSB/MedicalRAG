"""Agent LangGraph 状态图与编排流水线行为测试（Aegra v2 消息契约）。"""

from langchain_core.runnables import RunnableConfig

from medicalrag_agent.graph import build_graph
from medicalrag_core.chat.model import Analysis, ChatRequest, MemoryContext, Outcome
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


class FakeMemory:
    async def load(self, request):
        return MemoryContext()

    async def append(self, request, message):
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
                snippet="s",
                intent="disease-info",
                channel="hybrid",
                score=0.9,
            ),
        )


class FakeGenerator:
    async def generate(self, context):
        return "回答"


class StreamingGenerator(FakeGenerator):
    async def stream(self, context):
        for token in ["回", "答"]:
            yield token


class FakeRuns:
    async def create_run(self, request):
        return "run-1"

    async def record_state(self, run_id, state):
        pass

    async def complete(self, run_id, result):
        pass


def _pipeline(generator=None) -> ChatPipeline:
    return ChatPipeline(
        memory=FakeMemory(),
        classifier=FakeClassifier(),
        retriever=FakeRetriever(),
        generator=generator or FakeGenerator(),
        runs=FakeRuns(),
        tree=_TREE,
        retrieval_policy=RetrievalPolicy(version=1, context_cap=8),
    )


def _config(thread_id: str = "trace-1") -> RunnableConfig:
    return RunnableConfig(
        configurable={
            "thread_id": thread_id,
            "langgraph_auth_user": "u",
            "user_id": "u",
            "workspace_ids": ["w"],
        }
    )


async def test_graph_invokes_pipeline_with_messages_input_and_returns_result():
    graph = build_graph(_pipeline())
    state = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]}, config=_config()
    )
    assert state["result"].outcome is Outcome.ANSWERED
    assert state["result"].message == "回答"
    assert state["result"].trace_id == "trace-1"
    assert state["outcome"] == "answered"
    assert state["answer"] == "回答"
    assert len(state["evidence"]) == 1
    # Aegra v2 消息契约：messages 状态累积输入 + 输出；最后一条为本轮 AI 回答，结构化元数据随消息持久
    ai = state["messages"][-1]
    assert ai.type == "ai"
    assert ai.content == "回答"
    custom = ai.additional_kwargs["custom"]
    assert custom["outcome"] == "answered"
    assert custom["evidence"][0]["chunk_id"] == "c1"
    assert custom["safety"]["risk_class"] == "general"  # 默认策略下发 general 风险评估


async def test_graph_accepts_explicit_request_for_deterministic_direct_call():
    graph = build_graph(_pipeline())
    request = ChatRequest(question="高血压", conversation_id="c", user_id="u", workspace_id="w")
    state = await graph.ainvoke({"request": request}, config=_config())
    assert state["result"].outcome is Outcome.ANSWERED
    assert state["result"].message == "回答"


async def test_graph_streams_tokens_to_custom_channel():
    graph = build_graph(_pipeline(StreamingGenerator()))
    tokens: list[str] = []
    async for chunk in graph.astream(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=_config(),
        stream_mode="custom",
    ):
        if isinstance(chunk, dict) and "tokens" in chunk:
            tokens.append(chunk["tokens"])
    assert "".join(tokens) == "回答"


async def test_graph_reads_analysis_depth_from_configurable():
    seen: list[bool] = []

    class ProbePipeline(ChatPipeline):
        async def run_stream(self, request, trace_id=None):
            seen.append(request.analysis_depth)
            async for event in super().run_stream(request, trace_id=trace_id):
                yield event

    graph = build_graph(
        ProbePipeline(
            memory=FakeMemory(),
            classifier=FakeClassifier(),
            retriever=FakeRetriever(),
            generator=FakeGenerator(),
            runs=FakeRuns(),
            tree=_TREE,
            retrieval_policy=RetrievalPolicy(version=1, context_cap=8),
        )
    )
    await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=RunnableConfig(
            configurable={
                "thread_id": "trace-1",
                "langgraph_auth_user": "u",
                "workspace_ids": ["w"],
                "analysis_depth": True,
            }
        ),
    )
    assert seen == [True]
