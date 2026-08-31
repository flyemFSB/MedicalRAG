"""LangGraph StateGraph 图编排（apps/agent 模块；由 Aegra 运行时托管）。

基于单个 `orchestrate` 节点驱动领域核心的确定性流式聊天编排流水线（ChatPipeline.run_stream）：
业务状态转移、意图路由与安全短路逻辑均严格收敛在领域层，避免在 Agent 外围重复编写流程分支。
图状态字段（analysis、evidence、safety、answer、outcome、result）经由 Aegra 的 values 通道向外发布供客户端查询，
生成的 Token 增量通过 custom 通道实时流式写出。
流式事件 payload 统一复用领域层定义的 to_payload 单一出口（ADR 0080）。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from medicalrag_core.chat.model import ChatRequest
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.chat.stream import (
    AnalysisEvent,
    DoneEvent,
    EvidenceEvent,
    SafetyEvent,
    TokenEvent,
)


class AgentState(TypedDict, total=False):
    """LangGraph 运行时状态定义：包含请求入参与编排流水线逐步外露的结构化结果。"""

    request: ChatRequest
    analysis: Any
    evidence: list[dict[str, object]]
    safety: dict[str, object] | None
    answer: str
    outcome: str
    result: Any


def build_graph(pipeline: ChatPipeline) -> CompiledStateGraph:
    """构建受控编译图：通过单编排节点调用确定性流式流水线，交由 Aegra 框架进行状态持久化与托管。"""

    async def orchestrate(state: AgentState, config: RunnableConfig) -> dict[str, object]:
        request = state.get("request")
        if request is None:
            raise ValueError("AgentState 缺失 request 字段")
        writer = get_stream_writer()
        answer_parts: list[str] = []
        structured: dict[str, object] = {
            "analysis": None,
            "evidence": [],
            "safety": None,
            "answer": "",
            "outcome": "",
        }
        # 可观测性链路追踪关联键：Aegra 以 thread_id 聚合本次运行的追踪日志（Phoenix session id，ADR 0082）
        thread_id = (config.get("configurable") or {}).get("thread_id")
        async for event in pipeline.run_stream(request, trace_id=thread_id):
            if isinstance(event, TokenEvent):
                answer_parts.append(event.text)
                structured["answer"] = "".join(answer_parts)
                writer({"tokens": event.text})
            elif isinstance(event, AnalysisEvent):
                structured["analysis"] = event.to_payload()
            elif isinstance(event, EvidenceEvent):
                structured.update(evidence=event.to_payload()["evidence"])
            elif isinstance(event, SafetyEvent):
                structured.update(safety=event.to_payload())
            elif isinstance(event, DoneEvent):
                payload = event.to_payload()
                structured["result"] = event.result
                structured["outcome"] = event.result.outcome.value
                structured["answer"] = event.result.message
                # 证据与安全评估在结束事件中进行最终对齐（以防短路路径未单独触发前置流式事件）
                structured["evidence"] = payload["evidence"]
                structured["safety"] = (
                    event.result.safety.to_payload() if event.result.safety is not None else None
                )
        return structured

    builder = StateGraph(AgentState)
    builder.add_node("orchestrate", orchestrate)
    builder.add_edge(START, "orchestrate")
    builder.add_edge("orchestrate", END)
    return builder.compile()
