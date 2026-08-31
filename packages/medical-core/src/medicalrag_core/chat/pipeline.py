"""聊天编排核心（遵循规范 seam 约束：确定性状态排序与短路规则）。

编排阶段严格按序执行：记忆读取 → 意图分析 → 路由分发（引导澄清/系统响应/安全拦截/落地检索）→ 检索 →
证据融合 → 安全评估 → 模型生成 → 状态持久化。所有短路与排序决策均在此处收敛；外部适配器仅负责提供数据，
绝不干预执行流。客户端可在任意 await 点触发请求取消，此时 Run 状态必须如实转入 CANCELLED 终止态并向外重抛
（遵循规范 §1.4：不吞没取消信号）。

编排实例设计为无状态：单次 Run 的状态机与 run_id 仅在调用栈局部流转，支持高并发安全复用。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

from ..evidence.fusion import fuse
from ..evidence.rerank import Reranker
from ..evidence.retrieval_policy import RetrievalPolicy
from ..intent.node import IntentKind
from ..intent.slot import extract_slots
from ..intent.tree import IntentResolution, IntentTree
from ..safety.policy import RiskClass, SafetyAssessment, assess, short_circuit_message
from .model import (
    Analysis,
    ChatRequest,
    ChatResult,
    GenerationContext,
    IntentQuery,
    Message,
    MessageRole,
    Outcome,
)
from .ports import (
    Generator,
    IntentClassifier,
    Memory,
    ProviderUnavailableError,
    Retriever,
    RunRepository,
    StreamingGenerator,
)
from .run_state import ChatRunEvent, ChatRunState, transition
from .stream import (
    AnalysisEvent,
    ChatStreamEvent,
    DoneEvent,
    EvidenceEvent,
    SafetyEvent,
    TokenEvent,
)

# 产品预设默认文案；澄清与系统响应文案优先采用适配器输出，此处仅作为兜底。
DEFAULT_CLARIFICATION = "请补充说明您想问的具体内容（例如疾病、症状或检查相关的问题）。"
EMPTY_EVIDENCE_MESSAGE = "未能找到足够的相关医学资料来回答这个问题。"
FALLBACK_MESSAGE = "生成服务暂不可用，无法生成完整回答；以下为已检索证据，供您参考。"

_RISK_RANK = {
    RiskClass.GENERAL: 0,
    RiskClass.TREATMENT: 1,
    RiskClass.URGENT: 2,
    RiskClass.PROHIBITED: 3,
}

_ROUTE = tuple[
    ChatRunEvent, Outcome, str, SafetyAssessment | None
]  # 短路路由元组：驱动事件 + 终止结果类型 + 回答文案 + 安全评估


class ChatPipeline:
    """单次聊天请求的确定性编排器。

    开启分析深度（Analysis Depth，ADR 0069）仅会提高检索预算，不会放宽安全边界，
    亦不改变证据回答（Evidence Answer）契约。
    """

    def __init__(
        self,
        *,
        memory: Memory,
        classifier: IntentClassifier,
        retriever: Retriever,
        generator: Generator,
        runs: RunRepository,
        tree: IntentTree,
        retrieval_policy: RetrievalPolicy,
        reranker: Reranker | None = None,
        top_n: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self._memory = memory
        self._classifier = classifier
        self._retriever = retriever
        self._generator = generator
        self._runs = runs
        self._tree = tree
        self._policy = retrieval_policy
        self._reranker = reranker
        self._top_n = top_n
        self._threshold = threshold

    def _effective_policy(self, analysis_depth: bool) -> RetrievalPolicy:
        """计算生效检索策略：开启 Analysis Depth（ADR 0069）时加倍检索预算与证据上限，策略版本保持不变。"""
        if not analysis_depth:
            return self._policy
        return RetrievalPolicy(
            version=self._policy.version,
            context_cap=self._policy.context_cap * 2,
            channel_quotas=self._policy.channel_quotas,
            intent_quota=self._policy.intent_quota,
            intent_priority=self._policy.intent_priority,
        )

    async def run(self, request: ChatRequest, *, trace_id: str | None = None) -> ChatResult:
        """非流式执行单次聊天请求；若客户端取消则记录 CANCELLED 状态并原样重抛。"""
        result: ChatResult | None = None
        async for event in self.run_stream(request, trace_id=trace_id):
            if isinstance(event, DoneEvent):
                result = event.result
        assert result is not None
        return result

    async def run_stream(
        self, request: ChatRequest, *, trace_id: str | None = None
    ) -> AsyncIterator[ChatStreamEvent]:
        """类型化流式执行入口（按序输出阶段事件流）。

        事件发射顺序与确定性执行阶段完全一致；遇到取消时记录 CANCELLED 并向外重抛（规范 §1.4）。
        """
        run_id = await self._runs.create_run(request)
        try:
            await self._memory.append(request, Message(MessageRole.USER, request.question))
            async for event in self._execute_stream(
                request, trace_id, run_id, ChatRunState.ACCEPTED
            ):
                yield event
        except asyncio.CancelledError:
            await self._runs.record_state(run_id, ChatRunState.CANCELLED)
            raise

    async def _execute_stream(
        self,
        request: ChatRequest,
        trace_id: str | None,
        run_id: str,
        state: ChatRunState,
    ) -> AsyncIterator[ChatStreamEvent]:
        context = await self._memory.load(request)
        state = await self._step(state, ChatRunEvent.MEMORY_LOADED, run_id)
        policy = self._effective_policy(request.analysis_depth)

        analysis = await self._classifier.analyze(request, self._tree.eligible_leaves(), context)
        state = await self._step(state, ChatRunEvent.ANALYZED, run_id)
        yield AnalysisEvent(analysis)

        resolution = self._tree.resolve(
            analysis.candidates, top_n=self._top_n, threshold=self._threshold
        )
        route = self._route(analysis, resolution)
        if route is not None:
            event, outcome, message, safety = route
            state = await self._step(state, event, run_id)
            result = await self._finish(
                request,
                state,
                run_id,
                ChatResult(
                    outcome=outcome,
                    message=message,
                    run_id=run_id,
                    safety=safety,
                    trace_id=trace_id,
                ),
            )
            yield DoneEvent(result)
            return

        queries, clarification = self._build_queries(
            resolution, analysis.slots, analysis.rewritten_question
        )
        if not queries:
            state = await self._step(state, ChatRunEvent.ROUTE_GUIDANCE, run_id)
            result = await self._finish(
                request,
                state,
                run_id,
                ChatResult(
                    outcome=Outcome.GUIDANCE,
                    message=clarification,
                    run_id=run_id,
                    trace_id=trace_id,
                ),
            )
            yield DoneEvent(result)
            return

        state = await self._step(state, ChatRunEvent.ROUTE_RETRIEVAL, run_id)
        candidates = await self._retriever.retrieve(request, tuple(queries))
        if self._reranker is not None and candidates:
            candidates = await self._reranker.rerank(analysis.rewritten_question, candidates)
        fused = fuse(candidates, policy)
        if not fused.evidence:
            state = await self._step(state, ChatRunEvent.NO_EVIDENCE, run_id)
            result = await self._finish(
                request,
                state,
                run_id,
                ChatResult(
                    outcome=Outcome.EMPTY,
                    message=EMPTY_EVIDENCE_MESSAGE,
                    run_id=run_id,
                    trace_id=trace_id,
                    retrieval_policy_version=policy.version,
                ),
            )
            yield DoneEvent(result)
            return

        state = await self._step(state, ChatRunEvent.EVIDENCE_FOUND, run_id)
        safety = assess(
            max(resolution.nodes, key=lambda n: _RISK_RANK[n.safety_class]).safety_class
        )
        yield EvidenceEvent(fused.evidence)
        yield SafetyEvent(safety)

        message_parts: list[str] = []
        try:
            if isinstance(self._generator, StreamingGenerator):
                async for token in self._generator.stream(
                    GenerationContext(
                        question=request.question,
                        rewritten_question=analysis.rewritten_question,
                        evidence=fused.evidence,
                        memory=context,
                        safety=safety,
                        analysis=request.analysis_depth,
                    )
                ):
                    message_parts.append(token)
                    yield TokenEvent(token)
            else:
                token = await self._generator.generate(
                    GenerationContext(
                        question=request.question,
                        rewritten_question=analysis.rewritten_question,
                        evidence=fused.evidence,
                        memory=context,
                        safety=safety,
                        analysis=request.analysis_depth,
                    )
                )
                message_parts.append(token)
                yield TokenEvent(token)
        except ProviderUnavailableError:
            state = await self._step(state, ChatRunEvent.PROVIDER_FAILURE, run_id)
            result = await self._finish(
                request,
                state,
                run_id,
                ChatResult(
                    outcome=Outcome.FALLBACK,
                    message=FALLBACK_MESSAGE,
                    run_id=run_id,
                    evidence=fused.evidence,
                    trace_id=trace_id,
                    retrieval_policy_version=policy.version,
                ),
            )
            yield DoneEvent(result)
            return

        state = await self._step(state, ChatRunEvent.MODEL_COMPLETED, run_id)
        result = await self._finish(
            request,
            state,
            run_id,
            ChatResult(
                outcome=Outcome.ANSWERED,
                message="".join(message_parts),
                run_id=run_id,
                evidence=fused.evidence,
                safety=safety,
                trace_id=trace_id,
                retrieval_policy_version=policy.version,
            ),
        )
        yield DoneEvent(result)

    def _route(self, analysis: Analysis, resolution: IntentResolution) -> _ROUTE | None:
        """根据意图解析结果判定路由走向；若需执行落地检索则返回 None。"""
        if analysis.guidance_message or not resolution.known:
            return (
                ChatRunEvent.ROUTE_GUIDANCE,
                Outcome.GUIDANCE,
                analysis.guidance_message or DEFAULT_CLARIFICATION,
                None,
            )
        if any(n.safety_class is RiskClass.PROHIBITED for n in resolution.nodes):
            return (
                ChatRunEvent.ROUTE_SAFETY,
                Outcome.SAFETY,
                short_circuit_message(assess(RiskClass.PROHIBITED)),
                assess(RiskClass.PROHIBITED),
            )
        node = resolution.nodes[0]
        if node.kind is IntentKind.SYSTEM:
            return (
                ChatRunEvent.ROUTE_SYSTEM_ONLY,
                Outcome.SYSTEM_ONLY,
                analysis.system_message or node.prompt_template or "",
                None,
            )
        return None

    def _build_queries(
        self,
        resolution: IntentResolution,
        raw_slots: Mapping[str, Mapping[str, object]],
        rewritten_question: str,
    ) -> tuple[list[IntentQuery], str]:
        """为各落地意图提取槽位；缺失或包含非法必填槽位的意图将被跳过（遵循规范）。

        每个查询均携带重写后的问题作为检索主体（ADR 0036）。
        返回值格式为 (queries, clarification)：当 queries 为空时，clarification 为槽位补充引导语；否则为空字符串。
        """
        queries: list[IntentQuery] = []
        missing_names: set[str] = set()
        for node in resolution.nodes:
            if node.slot_schema is None:
                queries.append(IntentQuery(node, rewritten_question=rewritten_question))
                continue
            filling = extract_slots(node.slot_schema, raw_slots.get(node.id, {}))
            required = {d.name for d in node.slot_schema.slots if d.required}
            blocked = bool(filling.missing) or bool(required & filling.invalid.keys())
            if blocked:
                missing_names.update(filling.missing)
                missing_names.update(filling.invalid)
                continue
            # 可选槽位的非法值不参与检索（不在 values 中）；仅在必填缺失或非法时才放弃该意图。
            queries.append(
                IntentQuery(
                    node,
                    filling.values,
                    rewritten_question=rewritten_question,
                )
            )
        if queries:
            return queries, ""
        names = "、".join(sorted(missing_names))
        return [], f"请补充以下信息后继续：{names}。" if names else DEFAULT_CLARIFICATION

    async def _step(self, state: ChatRunState, event: ChatRunEvent, run_id: str) -> ChatRunState:
        state = transition(state, event)
        await self._runs.record_state(run_id, state)
        return state

    async def _finish(
        self, request: ChatRequest, state: ChatRunState, run_id: str, result: ChatResult
    ) -> ChatResult:
        # 短路分支目前处于中间状态（GUIDANCE/SYSTEM_ONLY/SAFETY/EMPTY/FALLBACK），
        # 需显式收敛为 COMPLETED 终止态；落地生成分支在 MODEL_COMPLETED 时已完成收敛。
        if state is not ChatRunState.COMPLETED:
            state = await self._step(state, ChatRunEvent.COMPLETE, run_id)
        await self._memory.append(request, Message(MessageRole.ASSISTANT, result.message))
        await self._runs.complete(run_id, result)
        return result
