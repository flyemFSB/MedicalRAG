"""Agent LangGraph 状态图与编排流水线行为测试（Aegra v2 消息契约）。"""

from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from medicalrag_agent.graph import build_graph
from medicalrag_core.chat.model import Analysis, MemoryContext
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

_USER = str(uuid4())
_WORKSPACE = str(uuid4())
_THREAD = str(uuid4())


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
    async def stream(self, context):
        for token in ["回", "答"]:
            yield token


class FakeRuns:
    async def create_run(self, request):
        return str(uuid4())

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


def _config(*, analysis_depth: bool = False) -> RunnableConfig:
    # 与 Aegra 注入形状一致：langgraph_auth_user 为认证处理器返回的用户对象/字典，
    # 自定义字段（workspace_ids）只随该对象传递。
    cf = {
        "thread_id": _THREAD,
        "langgraph_auth_user": {"identity": _USER, "workspace_ids": [_WORKSPACE]},
    }
    if analysis_depth:
        cf["analysis_depth"] = True
    return RunnableConfig(configurable=cf)


def _custom(state) -> dict:
    return state["messages"][-1].additional_kwargs["custom"]


async def test_graph_invokes_pipeline_with_messages_input_and_returns_result():
    graph = build_graph(_pipeline())
    state = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]}, config=_config()
    )
    assert len(state["evidence"]) == 1
    ai = state["messages"][-1]
    assert ai.type == "ai"
    assert ai.content == "回答"
    custom = _custom(state)
    assert custom["outcome"] == "answered"
    assert custom["evidence"][0]["chunk_id"] == "c1"
    assert custom["safety"]["risk_class"] == "general"


async def test_graph_rejects_invalid_uuid_identity():
    graph = build_graph(_pipeline())
    state = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=RunnableConfig(
            configurable={
                "thread_id": _THREAD,
                "langgraph_auth_user": {"identity": "anonymous", "workspace_ids": [_WORKSPACE]},
            }
        ),
    )
    # error_handler 将非法身份降级为 failed，避免裸异常打穿 Aegra
    assert _custom(state)["outcome"] == "failed"
    assert state["messages"][-1].content


async def test_graph_rejects_missing_workspace():
    graph = build_graph(_pipeline())
    state = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=RunnableConfig(
            configurable={
                "thread_id": _THREAD,
                "langgraph_auth_user": {"identity": _USER, "workspace_ids": []},
            }
        ),
    )
    assert _custom(state)["outcome"] == "failed"


async def test_graph_ignores_client_supplied_identity_and_workspace():
    """客户端 config 中的 user_id/workspace_ids 不得覆盖 Aegra 注入的身份（防越权读）。"""
    seen: list[str] = []

    class ProbePipeline(ChatPipeline):
        async def run_stream(self, request, trace_id=None):
            seen.append(f"{request.user_id}:{request.workspace_id}")
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
                "thread_id": _THREAD,
                "langgraph_auth_user": {"identity": _USER, "workspace_ids": [_WORKSPACE]},
                "user_id": str(uuid4()),
                "workspace_ids": [str(uuid4())],
            }
        ),
    )
    assert seen == [f"{_USER}:{_WORKSPACE}"]


async def test_graph_fails_closed_when_auth_context_missing():
    """fail-closed：认证上下文缺失（Aegra auth 误配置/绕过宿主直调）一律拒绝——
    客户端 config 自报的 user_id/workspace_ids 不得作为身份来源（跨工作区越权通道）。"""
    graph = build_graph(_pipeline())
    result = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=RunnableConfig(
            configurable={
                "thread_id": _THREAD,
                "user_id": _USER,
                "workspace_ids": [_WORKSPACE],
            }
        ),
    )
    # error_handler 将 ValueError 归类为请求非法：给出可诊断的失败降级而非执行检索
    assert _custom(result)["outcome"] == "failed"
    assert result["evidence"] == []


async def test_graph_streams_tokens_and_stages_to_custom_channel():
    graph = build_graph(_pipeline(FakeGenerator()))
    tokens: list[str] = []
    stages: set[str] = set()
    async for chunk in graph.astream(
        {"messages": [{"role": "human", "content": "高血压"}]},
        config=_config(),
        stream_mode="custom",
    ):
        if isinstance(chunk, dict):
            if "tokens" in chunk:
                tokens.append(chunk["tokens"])
            if "stage" in chunk:
                stages.add(chunk["stage"])
    assert "".join(tokens) == "回答"
    assert {"analysis", "evidence", "token"} <= stages


async def test_graph_error_handler_returns_failed_outcome():
    class BoomClassifier:
        async def analyze(self, request, leaves, context):
            raise ConnectionError("llm down")

    graph = build_graph(
        ChatPipeline(
            memory=FakeMemory(),
            classifier=BoomClassifier(),
            retriever=FakeRetriever(),
            generator=FakeGenerator(),
            runs=FakeRuns(),
            tree=_TREE,
            retrieval_policy=RetrievalPolicy(version=1, context_cap=8),
        )
    )
    state = await graph.ainvoke(
        {"messages": [{"role": "human", "content": "高血压"}]}, config=_config()
    )
    custom = _custom(state)
    assert custom["outcome"] == "failed"
    assert state["messages"][-1].content


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
        config=_config(analysis_depth=True),
    )
    assert seen == [True]
