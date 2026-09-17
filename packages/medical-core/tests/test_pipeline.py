"""聊天编排核心管线测试（覆盖规范流水线测试清单与短路决策逻辑）。"""

import asyncio

import pytest

from medicalrag_core.chat.model import (
    Analysis,
    ChatRequest,
    MemoryContext,
    Message,
    MessageRole,
    Outcome,
)
from medicalrag_core.chat.pipeline import (
    DEFAULT_CLARIFICATION,
    EMPTY_EVIDENCE_MESSAGE,
    FALLBACK_MESSAGE,
    ChatPipeline,
)
from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.chat.run_state import ChatRunState
from medicalrag_core.chat.stream import AnalysisEvent, DoneEvent
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentTree, ScoredIntent
from medicalrag_core.safety.policy import FIXED_DISCLAIMER, RiskClass

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
        IntentNode(
            "disease-treatment",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="治疗咨询",
            safety_class=RiskClass.TREATMENT,
        ),
        IntentNode(
            "urgent",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="急症",
            safety_class=RiskClass.URGENT,
        ),
        IntentNode(
            "diag",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="诊断",
            safety_class=RiskClass.PROHIBITED,
        ),
        IntentNode(
            "sys", level=IntentLevel.TOPIC, parent_id="medical", kind=IntentKind.SYSTEM, name="系统"
        ),
    ]
)


async def _run(pipeline: ChatPipeline, request: ChatRequest):
    """测试专用非流式收敛：从 run_stream 中提取 DoneEvent 的结果。"""
    async for event in pipeline.run_stream(request):
        if isinstance(event, DoneEvent):
            return event.result
    raise AssertionError("聊天流未产出 DoneEvent 即结束")


def _request(**overrides) -> ChatRequest:
    defaults = {
        "question": "高血压应该注意什么？",
        "conversation_id": "conv-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


def _candidate(**overrides) -> Candidate:
    defaults = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "source_id": "src-1",
        "title": "t",
        "snippet": "s",
        "intent": "disease-info",
        "channel": "dense",
        "score": 0.5,
    }
    defaults.update(overrides)
    return Candidate(**defaults)


class FakeMemory:
    def __init__(self) -> None:
        self.appended: list[Message] = []

    async def load(self, request: ChatRequest) -> MemoryContext:
        return MemoryContext()

    async def append(self, request: ChatRequest, message: Message) -> None:
        self.appended.append(message)


class FakeClassifier:
    def __init__(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.calls: list[tuple] = []

    async def analyze(self, request, leaves, context):
        self.calls.append((request, leaves, context))
        return self.analysis


class FakeRetriever:
    def __init__(self, candidates: tuple[Candidate, ...] = ()) -> None:
        self.candidates = candidates
        self.calls: list[tuple] = []

    async def retrieve(self, request, queries):
        self.calls.append((request, queries))
        return self.candidates


class FakeGenerator:
    def __init__(self, *, answer: str = "回答", error: BaseException | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list = []

    async def stream(self, context):
        self.calls.append(context)
        if self.error is not None:
            raise self.error
        yield self.answer


class FakeRuns:
    def __init__(self) -> None:
        self.states: list[tuple[str, ChatRunState]] = []
        self.completed: object | None = None
        self._n = 0

    async def create_run(self, request: ChatRequest) -> str:
        self._n += 1
        return f"run-{self._n}"

    async def record_state(self, run_id: str, state: ChatRunState) -> None:
        self.states.append((run_id, state))

    async def complete(self, run_id: str, result) -> None:
        self.completed = result


def _pipeline(
    *,
    analysis: Analysis,
    candidates: tuple[Candidate, ...] = (),
    answer: str = "回答",
    generator_error: BaseException | None = None,
    reranker=None,
    policy: RetrievalPolicy | None = None,
    term_intents=None,
    tree_loader=None,
    tree: IntentTree | None = None,
) -> tuple[ChatPipeline, FakeMemory, FakeClassifier, FakeRetriever, FakeGenerator, FakeRuns]:
    memory = FakeMemory()
    classifier = FakeClassifier(analysis)
    retriever = FakeRetriever(candidates)
    generator = FakeGenerator(answer=answer, error=generator_error)
    runs = FakeRuns()
    pipeline = ChatPipeline(
        memory=memory,
        classifier=classifier,
        retriever=retriever,
        generator=generator,
        runs=runs,
        tree=tree or _TREE,
        retrieval_policy=policy or RetrievalPolicy(version=1, context_cap=10),
        reranker=reranker,
        term_intents=term_intents,
        tree_loader=tree_loader,
    )
    return pipeline, memory, classifier, retriever, generator, runs


def _analysis(**overrides) -> Analysis:
    defaults = {
        "rewritten_question": "高血压注意事项",
        "candidates": (ScoredIntent("disease-info", 0.9),),
    }
    defaults.update(overrides)
    return Analysis(**defaults)


async def _events(pipeline: ChatPipeline, request: ChatRequest) -> list:
    """全量消费流（含终止后的收尾），模拟 SSE 端把生成器跑到结束。"""
    return [event async for event in pipeline.run_stream(request)]


class FakeTermIntents:
    """查询词映射端口替身：记录被调用的问题，返回运营配置命中的意图。"""

    def __init__(self, mapped: tuple[ScoredIntent, ...] = ()) -> None:
        self.mapped = mapped
        self.questions: list[str] = []

    async def resolve(self, question: str) -> tuple[ScoredIntent, ...]:
        self.questions.append(question)
        return self.mapped


async def test_tree_loader_refreshes_tree_at_run_start():
    """意图树热更新：每次 Run 开始时经 loader 重新加载（运营改树无需重启进程）。"""
    loaded = IntentTree(
        [
            IntentNode("medical", level=IntentLevel.DOMAIN, kind=IntentKind.KNOWLEDGE, name="医学"),
            IntentNode(
                "hot",
                level=IntentLevel.TOPIC,
                parent_id="medical",
                kind=IntentKind.KNOWLEDGE,
                name="热更新的主题",
            ),
        ]
    )
    calls: list[int] = []

    async def loader() -> IntentTree:
        calls.append(1)
        return loaded

    pipeline, _, classifier, _, _, _ = _pipeline(
        analysis=_analysis(), candidates=(_candidate(),), tree_loader=loader
    )
    await _events(pipeline, _request())

    assert len(calls) == 1
    assert {leaf.name for leaf in classifier.calls[0][1]} == {"热更新的主题"}


async def test_prohibited_question_short_circuits_before_retrieval_and_generation():
    """个体化临床决策请求：确定性前置闸门命中即短路，不检索、不生成（ADR 0043）。"""
    pipeline, _, _, retriever, generator, _ = _pipeline(analysis=_analysis())
    events = await _events(pipeline, _request(question="帮 我 开 一 下 处 方"))
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.result.outcome is Outcome.SAFETY
    assert done.result.safety is not None
    assert retriever.calls == []
    assert generator.calls == []


async def test_term_mapping_prepends_mapped_intent_candidates():
    """查询词映射是确定性捷径：命中的术语意图强制排在最前（运营配置可纠偏）。"""
    term_intents = FakeTermIntents((ScoredIntent("urgent", 0.5),))
    pipeline, _, _, _, _, _ = _pipeline(
        analysis=_analysis(candidates=(ScoredIntent("disease-info", 0.9),)),
        candidates=(_candidate(),),
        term_intents=term_intents,
    )
    events = await _events(pipeline, _request())
    analysis_event = next(event for event in events if isinstance(event, AnalysisEvent))

    assert [c.node_id for c in analysis_event.analysis.candidates] == ["urgent", "disease-info"]
    assert term_intents.questions == ["高血压应该注意什么？"]


async def test_term_mapping_without_hits_keeps_classifier_candidates():
    """词映射无命中（运营未配术语）时分析结果原样通过：不得清空或重排候选。"""
    term_intents = FakeTermIntents(())
    pipeline, _, _, _, _, _ = _pipeline(
        analysis=_analysis(candidates=(ScoredIntent("disease-info", 0.9),)),
        candidates=(_candidate(),),
        term_intents=term_intents,
    )
    events = await _events(pipeline, _request())
    analysis_event = next(event for event in events if isinstance(event, AnalysisEvent))

    assert [c.node_id for c in analysis_event.analysis.candidates] == ["disease-info"]
    assert term_intents.questions == ["高血压应该注意什么？"]


async def test_empty_evidence_stream_terminates_after_done_event():
    """空召回：DoneEvent 之后流必须结束（SSE 端依赖生成器终止，不得悬挂）。"""
    pipeline, _, _, _, _, _ = _pipeline(analysis=_analysis(), candidates=())
    events = await _events(pipeline, _request())

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].result.outcome is Outcome.EMPTY


async def test_provider_failure_stream_terminates_after_fallback_done():
    """生成提供方不可用：回落答案仍携带已召回证据，且流在 DoneEvent 后结束。"""
    pipeline, _, _, _, _, _ = _pipeline(
        analysis=_analysis(),
        candidates=(_candidate(),),
        generator_error=ProviderUnavailableError("boom"),
    )
    events = await _events(pipeline, _request())

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].result.outcome is Outcome.FALLBACK
    assert events[-1].result.evidence


async def test_consumer_closing_stream_records_cancelled_run():
    """消费方提前关闭流（SSE 断连）与取消同语义：如实记录 CANCELLED 后放行。"""
    pipeline, _, _, _, _, runs = _pipeline(analysis=_analysis(), candidates=(_candidate(),))
    stream = pipeline.run_stream(_request())
    await stream.__anext__()
    await stream.aclose()

    assert runs.states[-1][1] is ChatRunState.CANCELLED


async def test_unexpected_generator_failure_marks_run_failed_and_reraises():
    """非「提供方不可用」的意外故障：收敛为 FAILED（不让 Run 卡在中间态），异常照常上抛。"""
    pipeline, _, _, _, _, runs = _pipeline(
        analysis=_analysis(), candidates=(_candidate(),), generator_error=RuntimeError("boom")
    )
    with pytest.raises(RuntimeError, match="boom"):
        await _events(pipeline, _request())

    assert runs.states[-1][1] is ChatRunState.FAILED


async def test_sub_questions_extend_retrieval_queries_with_cap_and_dedupe():
    """子问题作为附加检索文本（扩展召回视角）：上限作用于原始列表，再逐条去空白、丢空串与重复项。"""
    pipeline, _, _, retriever, _, _ = _pipeline(
        analysis=_analysis(sub_questions=("  并发症  ", "", "高血压注意事项", "用药禁忌")),
        candidates=(_candidate(),),
    )
    await _events(pipeline, _request())

    # 上限 2 截的是原始列表（成本控制）；空串在清洗阶段被丢弃，故最终只有 1 条附加文本
    assert [q.rewritten_question for q in retriever.calls[0][1]] == ["高血压注意事项", "并发症"]


async def test_grounded_path_answers_with_evidence_and_safety():
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, retriever, generator, runs = _pipeline(
        analysis=analysis,
        candidates=(_candidate(), _candidate(chunk_id="chunk-2", score=0.8)),
    )
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.ANSWERED
    assert result.message == "回答"
    assert len(result.evidence) == 2
    assert result.safety is not None and result.safety.risk_class is RiskClass.GENERAL
    assert [q.node.id for q in retriever.calls[0][1]] == ["disease-info"]  # 解析出的落地意图
    assert generator.calls[0].evidence == result.evidence
    assert runs.completed is result
    assert runs.states[-1][1] is ChatRunState.COMPLETED


class FakeReranker:
    """重排器替身：可注入故障；正常时回填重排分数以验证重排结果确实参与排序。"""

    def __init__(self, error: BaseException | None = None) -> None:
        self.calls = 0
        self.input_sizes: list[int] = []
        self._error = error

    async def rerank(self, query, candidates):
        self.calls += 1
        self.input_sizes.append(len(candidates))
        if self._error is not None:
            raise self._error
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
                reranker_score=1.0,
            )
            for c in candidates
        )


async def test_reranker_failure_falls_back_to_channel_ranking():
    """ADR 0037：重排器故障（超时/配额/非法响应）必须回落通道分数，证据仍可用。"""
    analysis = Analysis(
        rewritten_question="高血压注意事项", candidates=(ScoredIntent("disease-info", 0.9),)
    )
    reranker = FakeReranker(error=ProviderUnavailableError("rerank down"))
    pipeline, *_ = _pipeline(analysis=analysis, candidates=(_candidate(),), reranker=reranker)
    result = await _run(pipeline, _request())
    assert reranker.calls == 1
    assert result.outcome is Outcome.ANSWERED
    assert result.evidence[0].score == 0.5  # 派生分 = 通道原始分


async def test_intent_below_confidence_floor_falls_back_to_guidance():
    """policy v2（ADR 0087）：低于 intent_min_score 的候选不进检索，走澄清引导兜底。"""
    analysis = Analysis(
        rewritten_question="模糊的问题",
        candidates=(ScoredIntent("disease-info", 0.2),),
    )
    policy = RetrievalPolicy(version=2, context_cap=10, intent_min_score=0.35)
    pipeline, _, _, retriever, generator, _ = _pipeline(analysis=analysis, policy=policy)
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.GUIDANCE
    assert retriever.calls == []
    assert generator.calls == []


async def test_intent_floor_can_be_disabled():
    """intent_min_score=0 关闭下限：低分已知意图照常落地检索。"""
    analysis = Analysis(
        rewritten_question="高血压注意事项", candidates=(ScoredIntent("disease-info", 0.2),)
    )
    policy = RetrievalPolicy(version=2, context_cap=10, intent_min_score=0.0)
    pipeline, _, _, retriever, _, _ = _pipeline(
        analysis=analysis, candidates=(_candidate(),), policy=policy
    )
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.ANSWERED
    assert len(retriever.calls) == 1


async def test_rerank_candidate_cap_limits_rerank_cost():
    """policy v2（ADR 0087）：重排只对通道分最高的前 N 个候选付费；截断候选保留通道分参与融合。"""
    analysis = Analysis(
        rewritten_question="高血压注意事项", candidates=(ScoredIntent("disease-info", 0.9),)
    )
    candidates = tuple(
        _candidate(chunk_id=f"chunk-{i}", score=0.1 + i / 100) for i in range(10)
    )  # 通道分 0.10 ~ 0.19
    reranker = FakeReranker()
    policy = RetrievalPolicy(version=2, context_cap=10, rerank_candidate_limit=3)
    pipeline, _, _, _, _, _ = _pipeline(
        analysis=analysis, candidates=candidates, reranker=reranker, policy=policy
    )
    result = await _run(pipeline, _request())
    assert reranker.calls == 1
    assert reranker.input_sizes == [3]  # 成本天花板生效
    # 重排后的 3 个最高分候选获得 reranker_score=1.0 占据证据前列
    top_ids = {e.chunk_id for e in result.evidence[:3]}
    assert top_ids == {"chunk-7", "chunk-8", "chunk-9"}
    # 截断的 7 个候选未丢失，仍以通道分参与融合排序（context_cap=10 全部入选）
    assert len(result.evidence) == 10


async def test_reranker_scores_drive_derived_ranking():
    analysis = Analysis(
        rewritten_question="高血压注意事项", candidates=(ScoredIntent("disease-info", 0.9),)
    )
    pipeline, *_ = _pipeline(analysis=analysis, candidates=(_candidate(),), reranker=FakeReranker())
    result = await _run(pipeline, _request())
    assert result.evidence[0].score == 1.0  # 派生分 = 重排分


async def test_treatment_notice_is_carried_not_embedded():
    analysis = Analysis(
        rewritten_question="高血压怎么治疗",
        candidates=(ScoredIntent("disease-treatment", 0.9),),
    )
    pipeline, _, _, _, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.ANSWERED
    assert result.safety is not None and result.safety.risk_class is RiskClass.TREATMENT
    assert result.safety.scope_notice is not None
    assert result.safety.scope_notice not in result.message  # 提示不拼入模型文本（ADR 0042）


async def test_system_only_short_circuits_before_retrieval():
    analysis = Analysis(
        rewritten_question="你是谁",
        candidates=(ScoredIntent("sys", 0.9),),
        system_message="我是医疗知识助手。",
    )
    pipeline, _, _, retriever, generator, runs = _pipeline(analysis=analysis)
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.SYSTEM_ONLY
    assert result.message == "我是医疗知识助手。"
    assert retriever.calls == []
    assert generator.calls == []
    assert runs.states[-1][1] is ChatRunState.COMPLETED


async def test_guidance_short_circuit_with_classifier_message():
    analysis = Analysis(
        rewritten_question="高血压",
        candidates=(ScoredIntent("disease-info", 0.5), ScoredIntent("urgent", 0.5)),
        guidance_message="您是指高血压的疾病信息，还是需要急症评估？",
    )
    pipeline, _, _, retriever, generator, _ = _pipeline(analysis=analysis)
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.GUIDANCE
    assert result.message == "您是指高血压的疾病信息，还是需要急症评估？"
    assert retriever.calls == []
    assert generator.calls == []


async def test_guidance_when_no_known_candidate():
    analysis = Analysis(
        rewritten_question="不明问题",
        candidates=(ScoredIntent("ghost", 0.9),),
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis)
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.GUIDANCE
    assert result.message == DEFAULT_CLARIFICATION
    assert retriever.calls == []


async def test_prohibited_short_circuits_before_retrieval_and_generation():
    analysis = Analysis(
        rewritten_question="我胸痛是不是心梗",
        candidates=(ScoredIntent("diag", 0.9),),
    )
    pipeline, _, _, retriever, generator, _ = _pipeline(analysis=analysis)
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.SAFETY
    assert FIXED_DISCLAIMER in result.message
    assert result.safety is not None and result.safety.prohibited
    assert retriever.calls == []
    assert generator.calls == []


async def test_empty_retrieval_path():
    analysis = Analysis(
        rewritten_question="罕见病资料",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, _, generator, _ = _pipeline(analysis=analysis, candidates=())
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.EMPTY
    assert result.message == EMPTY_EVIDENCE_MESSAGE
    assert result.evidence == ()
    assert generator.calls == []


async def test_provider_failure_returns_fallback_with_evidence():
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, _, _, _ = _pipeline(
        analysis=analysis,
        candidates=(_candidate(),),
        generator_error=ProviderUnavailableError(),
    )
    result = await _run(pipeline, _request())
    assert result.outcome is Outcome.FALLBACK
    assert result.message == FALLBACK_MESSAGE
    assert len(result.evidence) == 1


async def test_cancellation_records_cancelled_and_reraises():
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, _, _, runs = _pipeline(
        analysis=analysis,
        candidates=(_candidate(),),
        generator_error=asyncio.CancelledError(),
    )
    with pytest.raises(asyncio.CancelledError):
        await _run(pipeline, _request())
    assert ChatRunState.CANCELLED in [state for _, state in runs.states]


async def test_concurrent_runs_on_shared_pipeline_do_not_interfere():
    # 实例无状态：同一 ChatPipeline 并发复用不串 run_id/state。
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, _, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    first, second = await asyncio.gather(
        _run(pipeline, _request(question="Q1")),
        _run(pipeline, _request(question="Q2")),
    )
    assert {first.run_id, second.run_id} == {"run-1", "run-2"}
    assert first.message == "回答"
    assert second.message == "回答"


async def test_user_and_assistant_messages_are_persisted():
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, memory, _, _, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    await _run(pipeline, _request(question="高血压应该注意什么？"))
    assert [m.role for m in memory.appended] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert memory.appended[0].text == "高血压应该注意什么？"
    assert memory.appended[1].text == "回答"
