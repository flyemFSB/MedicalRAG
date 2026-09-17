"""聊天编排核心（遵循规范 seam 约束：确定性状态排序与短路规则）。

编排阶段严格按序执行：记忆读取 → 意图分析 → 路由分发（引导澄清/系统响应/安全拦截/落地检索）→ 检索 →
证据融合 → 安全评估 → 模型生成 → 状态持久化。所有短路与排序决策均在此处收敛；外部适配器仅负责提供数据，
绝不干预执行流。客户端可在任意 await 点触发请求取消，此时 Run 状态必须如实转入 CANCELLED 终止态并向外重抛
（遵循规范 §1.4：不吞没取消信号）。

编排实例设计为无状态：单次 Run 的状态机与 run_id 仅在调用栈局部流转，支持高并发安全复用。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import replace

from ..evidence.fusion import fuse
from ..evidence.rerank import Reranker
from ..evidence.retrieval_policy import RetrievalPolicy
from ..intent.node import IntentKind
from ..intent.tree import IntentResolution, IntentTree
from ..safety.policy import (
    RiskClass,
    SafetyAssessment,
    assess,
    detect_prohibited,
    short_circuit_message,
)
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
    TermIntentResolver,
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

# 单次检索携带的子问题数上限（问题重写 + 拆分产出；防止查询数爆炸）
_MAX_SUB_QUESTIONS = 3

_ROUTE = tuple[
    ChatRunEvent, Outcome, str, SafetyAssessment | None
]  # 短路路由元组：驱动事件 + 终止结果类型 + 回答文案 + 安全评估


class ChatPipeline:
    """单次聊天请求的确定性编排器。

    开启分析深度（Analysis Depth）仅会提高检索预算，不会放宽安全边界，
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
        term_intents: TermIntentResolver | None = None,
        tree_loader: Callable[[], Awaitable[IntentTree]] | None = None,
    ) -> None:
        self._memory = memory
        self._classifier = classifier
        self._retriever = retriever
        self._generator = generator
        self._runs = runs
        self._tree = tree
        self._policy = retrieval_policy
        self._reranker = reranker
        self._term_intents = term_intents
        self._tree_loader = tree_loader

    def _effective_policy(self, analysis_depth: bool) -> RetrievalPolicy:
        """计算生效检索策略：开启 Analysis Depth 时加倍检索预算，策略版本保持不变。"""
        if not analysis_depth:
            return self._policy
        return replace(self._policy, context_cap=self._policy.context_cap * 2)

    async def run_stream(
        self, request: ChatRequest, *, trace_id: str | None = None
    ) -> AsyncIterator[ChatStreamEvent]:
        """类型化流式执行入口（按序输出阶段事件流）。

        事件发射顺序与确定性执行阶段完全一致；遇到取消时记录 CANCELLED 并向外重抛（规范 §1.4）。
        DoneEvent 发出后 Run 已完成落库，任何后续异常/关闭都不得把终态改写为 FAILED/CANCELLED。
        """
        run_id = await self._runs.create_run(request)
        completed = False
        try:
            await self._memory.append(request, Message(MessageRole.USER, request.question))
            async for event in self._execute_stream(
                request, trace_id, run_id, ChatRunState.ACCEPTED
            ):
                if isinstance(event, DoneEvent):
                    completed = True
                yield event
        except GeneratorExit:
            # 消费方提前关闭流（aclose）：与取消同语义，如实记录 CANCELLED 后放行
            if not completed:
                with suppress(Exception):
                    await self._runs.record_state(run_id, ChatRunState.CANCELLED)
            raise
        except asyncio.CancelledError:
            if not completed:
                await self._runs.record_state(run_id, ChatRunState.CANCELLED)
            raise
        except Exception:
            # 非 Provider 不可用的意外故障：收敛为 FAILED，避免 Run 卡在中间态。
            # completed=True 一侧当前不可达：DoneEvent 是 _execute_stream 每条路径的最后一次产出，
            # 其后没有代码可以抛错。守卫仍须保留（产出 DoneEvent 之后再抛错不得把已完成 Run
            # 改写成 FAILED，同 _finish 的顺序不变量），故显式声明「无分支」而不是补一个永不失败的测试。
            if not completed:  # pragma: no branch
                with suppress(Exception):
                    await self._runs.record_state(run_id, ChatRunState.FAILED)
            raise

    async def _execute_stream(
        self,
        request: ChatRequest,
        trace_id: str | None,
        run_id: str,
        state: ChatRunState,
    ) -> AsyncIterator[ChatStreamEvent]:
        if self._tree_loader is not None:
            # 意图树热更新：每次 Run 开始时经 TTL 缓存加载，运营台改树后无需重启
            self._tree = await self._tree_loader()
        context = await self._memory.load(request)
        state = await self._step(state, ChatRunEvent.MEMORY_LOADED, run_id)
        policy = self._effective_policy(request.analysis_depth)

        # 确定性违规前置拦截（ADR 0043）：不依赖外部模型，命中即短路，不检索、不生成
        if detect_prohibited(request.question):
            state = await self._step(state, ChatRunEvent.ROUTE_SAFETY, run_id)
            result = await self._finish(
                request,
                state,
                run_id,
                ChatResult(
                    outcome=Outcome.SAFETY,
                    message=short_circuit_message(assess(RiskClass.PROHIBITED)),
                    run_id=run_id,
                    safety=assess(RiskClass.PROHIBITED),
                    trace_id=trace_id,
                ),
            )
            yield DoneEvent(result)
            return

        analysis = await self._classifier.analyze(request, self._tree.eligible_leaves(), context)
        if self._term_intents is not None:
            # 查询词映射（运营配置的确定性捷径）：命中的术语意图强制纳入候选首位
            mapped = await self._term_intents.resolve(request.question)
            if mapped:
                existing = {candidate.node_id for candidate in analysis.candidates}
                analysis = replace(
                    analysis,
                    candidates=tuple(m for m in mapped if m.node_id not in existing)
                    + analysis.candidates,
                )
        state = await self._step(state, ChatRunEvent.ANALYZED, run_id)
        yield AnalysisEvent(analysis)

        # 意图置信度下限（policy v2）：低分候选不进检索——宁可触发澄清引导，不拿弱意图硬检索
        resolution = self._tree.resolve(
            analysis.candidates, threshold=policy.intent_min_score or None
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

        queries = self._build_queries(resolution, analysis)

        state = await self._step(state, ChatRunEvent.ROUTE_RETRIEVAL, run_id)
        candidates = await self._retriever.retrieve(request, tuple(queries))
        if self._reranker is not None and candidates:
            # 重排候选池上限（policy v2，成本天花板）：只对通道分最高的前 N 个候选支付精排费用；
            # 重排分数按 chunk_id 回填全量候选集——被截断候选保留通道原分参与融合，不因截断丢失。
            if (
                policy.rerank_candidate_limit > 0
                and len(candidates) > policy.rerank_candidate_limit
            ):
                capped = tuple(
                    sorted(candidates, key=lambda c: (-c.score, c.chunk_id))[
                        : policy.rerank_candidate_limit
                    ]
                )
            else:
                capped = candidates
            # ADR 0037：重排器故障/配额/非法响应回落多路融合的原始通道分数，
            # 不因调序器不可用而使已召回的证据不可答。
            with suppress(ProviderUnavailableError):
                reranked = await self._reranker.rerank(analysis.rewritten_question, capped)
                rerank_scores = {c.chunk_id: c.reranker_score for c in reranked}
                candidates = tuple(
                    replace(c, reranker_score=rerank_scores.get(c.chunk_id)) for c in candidates
                )
        evidence_items = fuse(candidates, policy)
        # 证据闸门（Evidence Gate）：整批证据的最高分未达阈值即拒答——库里没有可靠答案时不硬答
        gate_blocked = (
            policy.evidence_min_score > 0
            and bool(evidence_items)
            and max(e.score for e in evidence_items) < policy.evidence_min_score
        )
        if not evidence_items or gate_blocked:
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
        yield EvidenceEvent(evidence_items)
        yield SafetyEvent(safety)

        message_parts: list[str] = []
        try:
            gen_context = GenerationContext(
                question=request.question,
                rewritten_question=analysis.rewritten_question,
                evidence=evidence_items,
                memory=context,
                safety=safety,
                analysis=request.analysis_depth,
            )
            async for token in self._generator.stream(gen_context):
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
                    evidence=evidence_items,
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
                evidence=evidence_items,
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

    def _build_queries(self, resolution: IntentResolution, analysis: Analysis) -> list[IntentQuery]:
        """构建落地检索查询：每个命中意图 × 每条查询文本（重写问题 + 拆分子问题）。

        每个意图的查询主体为重写后的问题；问题重写阶段拆分出的子问题作为附加查询文本
        并发参与检索（扩展召回视角，上下限由 Analysis 产出方控制）。
        """
        query_texts = [analysis.rewritten_question]
        for sub in analysis.sub_questions[:_MAX_SUB_QUESTIONS]:
            sub = sub.strip()
            if sub and sub not in query_texts:
                query_texts.append(sub)
        return [
            IntentQuery(node, rewritten_question=text)
            for node in resolution.nodes
            for text in query_texts
        ]

    async def _step(self, state: ChatRunState, event: ChatRunEvent, run_id: str) -> ChatRunState:
        state = transition(state, event)
        await self._runs.record_state(run_id, state)
        return state

    async def _finish(
        self, request: ChatRequest, state: ChatRunState, run_id: str, result: ChatResult
    ) -> ChatResult:
        # 先落库助手消息与运行结果（complete 本身即写入 COMPLETED 终止态），最后补记状态机
        # COMPLETE 事件：若顺序颠倒，append/complete 在 COMPLETED 记录之后的失败会把已完成的
        # Run 改写为 FAILED，破坏终止态权威性（运营台审计真相）。
        assistant_id = await self._memory.append(
            request, Message(MessageRole.ASSISTANT, result.message)
        )
        result = replace(result, message_id=assistant_id)
        await self._runs.complete(run_id, result)
        if state is not ChatRunState.COMPLETED:
            # 短路分支（GUIDANCE/SAFETY/EMPTY/FALLBACK 等）显式收敛为 COMPLETED；
            # complete() 已落库终态，此处仅为补全状态机事件轨迹，失败不改变已完成事实
            with suppress(Exception):
                await self._step(state, ChatRunEvent.COMPLETE, run_id)
        return result
