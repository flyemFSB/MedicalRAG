"""LangGraph StateGraph 图编排（apps/agent 模块；由 Aegra 运行时托管）。

基于单个 `orchestrate` 节点驱动领域核心的确定性流式聊天编排流水线（ChatPipeline.run_stream）：
业务状态转移、意图路由与安全短路逻辑均收敛在领域层，不在 Agent 外围重复编写流程分支。

Aegra v2 消费契约：
- 输入：`messages` 状态键（LangChain 兼容消息；assistant-ui 官方桥经 run.start 下发 user 消息）；
  会话/用户/工作区/分析深度来自 LangGraph run config 的 `configurable`（Aegra auth 注入 + assistant-ui
  `append(..., { runConfig: { custom } })` 官方桥透传）。
- 输出：`messages` 键写入完整 AI 回答（`add_messages` 累积）；证据/安全/结果写入 state values 通道
  （前端 `useLangChainState` 读取），并经 `AIMessage.additional_kwargs["custom"]` 随消息持久
  （assistant-ui 官方桥透传为消息 `metadata.custom`，保证每条历史回答的证据可溯源）。
- Token 增量经 custom 通道实时流式写出（`get_stream_writer`，官方推荐）。
流式事件 payload 统一复用领域层定义的 to_payload 单一出口。
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

from medicalrag_core.chat.model import ChatRequest
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.chat.stream import DoneEvent, TokenEvent


class AgentState(TypedDict, total=False):
    """LangGraph 运行时状态定义：Aegra v2 消息契约 + 编排流水线逐步外露的结构化结果。"""

    request: ChatRequest  # 兼容直连（确定性测试）：优先于 messages 输入
    messages: Annotated[list[AnyMessage], add_messages]
    analysis: Any
    evidence: list[dict[str, object]]
    safety: dict[str, object] | None
    answer: str
    outcome: str
    result: Any


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _request(state: AgentState, config: RunnableConfig) -> ChatRequest:
    """由显式 request 或 Aegra v2 输入（messages + configurable）构造领域请求。"""
    request = state.get("request")
    if request is not None:
        return request
    cf = config.get("configurable") or {}
    thread_id = str(cf.get("thread_id") or "local")
    user_id = str(cf.get("langgraph_auth_user") or cf.get("user_id") or "anonymous")
    workspace_ids = cf.get("workspace_ids") or []
    # 工作区缺省回落 user_id：按不存在的工作区过滤得到空召回，不会越权暴露；
    # 等 Aegra 会话携带工作区上下文后可移除回落。
    workspace_id = str(workspace_ids[0] if workspace_ids else (cf.get("workspace_id") or user_id))
    messages = state.get("messages") or []
    question = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage) and m.content),
        "",
    )
    if not question:
        raise ValueError("AgentState 缺少 request 且输入 messages 中无 user 消息")
    return ChatRequest(
        question=str(question),
        conversation_id=thread_id,
        user_id=user_id,
        workspace_id=workspace_id,
        analysis_depth=_as_bool(cf.get("analysis_depth")),
    )


def build_graph(pipeline: ChatPipeline) -> CompiledStateGraph:
    """构建受控编译图：通过单编排节点调用确定性流式流水线，交由 Aegra 框架进行状态持久化与托管。"""

    async def orchestrate(state: AgentState, config: RunnableConfig) -> dict[str, object]:
        request = _request(state, config)
        writer = get_stream_writer()
        result = None
        async for event in pipeline.run_stream(
            request, trace_id=(config.get("configurable") or {}).get("thread_id")
        ):
            if isinstance(event, TokenEvent):
                # token 增量仅经 custom 通道流式直出；完整回答以 DoneEvent 结果为准
                writer({"tokens": event.text})
            elif isinstance(event, DoneEvent):
                result = event.result
        if result is None:
            raise RuntimeError("编排流水线未产出结束事件")
        payload = DoneEvent(result).to_payload()
        safety_payload = result.safety.to_payload() if result.safety is not None else None
        structured: dict[str, object] = {
            "evidence": payload["evidence"],
            "safety": safety_payload,
            "answer": result.message,
            "outcome": result.outcome.value,
            "result": result,
        }
        # 官方桥（assistant-ui react-langchain）：additional_kwargs → 消息 metadata.custom，
        # 随消息持久，保证每条历史回答的证据与安全评估可溯源（医疗证据边界）。
        ai = AIMessage(
            id=str(uuid4()),
            content=result.message,
            additional_kwargs={
                "custom": {
                    "evidence": payload["evidence"],
                    "safety": safety_payload,
                    "outcome": result.outcome.value,
                }
            },
        )
        structured["messages"] = [ai]
        return structured

    builder = StateGraph(AgentState)
    builder.add_node("orchestrate", orchestrate)
    builder.add_edge(START, "orchestrate")
    builder.add_edge("orchestrate", END)
    return builder.compile()
