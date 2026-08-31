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
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.slot import SlotDefinition, SlotSchema, SlotType
from medicalrag_core.intent.tree import IntentTree, ScoredIntent
from medicalrag_core.safety.policy import FIXED_DISCLAIMER, RiskClass

_SLOT_SCHEMA = SlotSchema(
    slots=(
        SlotDefinition(
            "department", SlotType.ENUM, required=True, enum_values=("心内科", "呼吸科")
        ),
        SlotDefinition("age_group", SlotType.ENUM, enum_values=("成人", "儿童")),
    )
)

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
            "department-info",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="科室疾病信息",
            slot_schema=_SLOT_SCHEMA,
        ),
        IntentNode(
            "sys", level=IntentLevel.TOPIC, parent_id="medical", kind=IntentKind.SYSTEM, name="系统"
        ),
    ]
)


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

    async def generate(self, context):
        self.calls.append(context)
        if self.error is not None:
            raise self.error
        return self.answer


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
        tree=_TREE,
        retrieval_policy=RetrievalPolicy(version=1, context_cap=10),
    )
    return pipeline, memory, classifier, retriever, generator, runs


async def test_grounded_path_answers_with_evidence_and_safety():
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, retriever, generator, runs = _pipeline(
        analysis=analysis,
        candidates=(_candidate(), _candidate(chunk_id="chunk-2", score=0.8)),
    )
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.ANSWERED
    assert result.message == "回答"
    assert len(result.evidence) == 2
    assert result.safety is not None and result.safety.risk_class is RiskClass.GENERAL
    assert [q.node.id for q in retriever.calls[0][1]] == ["disease-info"]  # 解析出的落地意图
    assert generator.calls[0].evidence == result.evidence
    assert runs.completed is result
    assert runs.states[-1][1] is ChatRunState.COMPLETED


async def test_treatment_notice_is_carried_not_embedded():
    analysis = Analysis(
        rewritten_question="高血压怎么治疗",
        candidates=(ScoredIntent("disease-treatment", 0.9),),
    )
    pipeline, _, _, _, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
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
    result = await pipeline.run(_request())
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
    result = await pipeline.run(_request())
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
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.GUIDANCE
    assert result.message == DEFAULT_CLARIFICATION
    assert retriever.calls == []


async def test_prohibited_short_circuits_before_retrieval_and_generation():
    analysis = Analysis(
        rewritten_question="我胸痛是不是心梗",
        candidates=(ScoredIntent("diag", 0.9),),
    )
    pipeline, _, _, retriever, generator, _ = _pipeline(analysis=analysis)
    result = await pipeline.run(_request())
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
    result = await pipeline.run(_request())
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
    result = await pipeline.run(_request())
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
        await pipeline.run(_request())
    assert ChatRunState.CANCELLED in [state for _, state in runs.states]


async def test_concurrent_runs_on_shared_pipeline_do_not_interfere():
    # 实例无状态：同一 ChatPipeline 并发复用不串 run_id/state。
    analysis = Analysis(
        rewritten_question="高血压注意事项",
        candidates=(ScoredIntent("disease-info", 0.9),),
    )
    pipeline, _, _, _, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    first, second = await asyncio.gather(
        pipeline.run(_request(question="Q1")),
        pipeline.run(_request(question="Q2")),
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
    await pipeline.run(_request(question="高血压应该注意什么？"))
    assert [m.role for m in memory.appended] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert memory.appended[0].text == "高血压应该注意什么？"
    assert memory.appended[1].text == "回答"


async def test_missing_required_slot_produces_slot_clarification():
    analysis = Analysis(
        rewritten_question="心内科疾病信息",
        candidates=(ScoredIntent("department-info", 0.9),),
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.GUIDANCE
    assert "department" in result.message
    assert retriever.calls == []


async def test_invalid_slot_value_skips_intent():
    analysis = Analysis(
        rewritten_question="心内科疾病信息",
        candidates=(ScoredIntent("department-info", 0.9),),
        slots={"department-info": {"department": "不存在科室"}},
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.GUIDANCE
    assert "department" in result.message
    assert retriever.calls == []


async def test_invalid_optional_slot_does_not_block_retrieval():
    # 可选槽位非法值被丢弃，不阻塞落地检索；必填非法才跳过（spec 语义）。
    analysis = Analysis(
        rewritten_question="心内科疾病信息",
        candidates=(ScoredIntent("department-info", 0.9),),
        slots={"department-info": {"department": "心内科", "age_group": "少年"}},
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.ANSWERED
    assert retriever.calls[0][1][0].slots == {"department": "心内科"}


async def test_complete_slots_pass_to_retriever():
    analysis = Analysis(
        rewritten_question="心内科疾病信息",
        candidates=(ScoredIntent("department-info", 0.9),),
        slots={"department-info": {"department": "心内科", "age_group": "儿童"}},
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.ANSWERED
    query = retriever.calls[0][1][0]
    assert query.node.id == "department-info"
    assert query.slots == {"department": "心内科", "age_group": "儿童"}


async def test_some_intents_missing_slot_keep_others_active():
    # 缺槽位的子意图被跳过，其余子意图保持活动（spec 用户故事 5）。
    analysis = Analysis(
        rewritten_question="心内科疾病和高血压",
        candidates=(ScoredIntent("department-info", 0.9), ScoredIntent("disease-info", 0.8)),
        slots={"department-info": {}},
    )
    pipeline, _, _, retriever, _, _ = _pipeline(analysis=analysis, candidates=(_candidate(),))
    result = await pipeline.run(_request())
    assert result.outcome is Outcome.ANSWERED
    assert [q.node.id for q in retriever.calls[0][1]] == ["disease-info"]
