"""LangGraph StateGraph 图编排（apps/agent；由 Aegra 托管）。

官方内置用法：
- MessagesState 风格 messages + add_messages
- get_stream_writer → custom 流（阶段进度 / token）
- TimeoutPolicy / error_handler + Command（fault-tolerance ≥1.2）
- Aegra 拥有 checkpointer；本图 compile 不挂 checkpointer

业务编排仍在 medical-core ChatPipeline；本图只做宿主契约与失败安全降级。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Annotated, TypedDict
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, TimeoutPolicy

from medicalrag_core.chat.model import ChatRequest, ChatResult
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.chat.stream import (
    AnalysisEvent,
    DoneEvent,
    EvidenceEvent,
    SafetyEvent,
    TokenEvent,
)
from medicalrag_infra.logging import logger
from medicalrag_infra.persistence.run_repository import ConversationBusyError

_FAILURE_MESSAGE = "服务暂时不可用，请稍后重试。"
_INVALID_REQUEST_MESSAGE = "请求上下文不完整，已拒绝执行。"
_BUSY_MESSAGE = "当前会话已有进行中的回答，请稍候。"


def _degraded_ai(message: str) -> AIMessage:
    """降级兜底消息（失败/拒答统一形态）：outcome=failed、无证据。"""
    return AIMessage(
        id=str(uuid4()),
        content=message,
        additional_kwargs={"custom": {"outcome": "failed", "evidence": [], "safety": None}},
    )


class AgentState(TypedDict, total=False):
    """Aegra v2 消息契约 + 证据通道。

    结论/安全/证据同时存在于末条 AIMessage 的 ``additional_kwargs["custom"]``；此处只保留
    前端 ``values`` 通道确实读取的 ``evidence``，避免同一份回答在每个 superstep 重复写入 checkpoint。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    evidence: list[dict[str, object]]


def _as_list(value: object) -> list[object]:
    """把可选的序列型上下文值归一为 list（非序列/缺失均为空表）。"""
    return list(value) if isinstance(value, (list, tuple)) else []


def _auth_context(cf: Mapping[str, object]) -> tuple[object, list[object]]:
    """解析 Aegra 注入的认证上下文（身份与成员工作区）。

    Aegra 把 ``@auth.authenticate`` 的返回值挂在 ``configurable.langgraph_auth_user``
    （对象或 dict），仅把 identity/display_name 复制到同名顶层键；自定义字段（workspace_ids）
    只随 langgraph_auth_user 传递。顶层 ``user_id`` 可被客户端 config 任意伪造，绝不作为身份来源。
    """
    raw = cf.get("langgraph_auth_user")
    if isinstance(raw, Mapping):
        return raw.get("identity"), _as_list(raw.get("workspace_ids"))
    if raw is not None:
        return getattr(raw, "identity", None), _as_list(getattr(raw, "workspace_ids", None))
    # fail-closed：认证上下文缺失（aegra.json auth.path 误配置/绕过宿主直调）一律拒绝执行。
    # 绝不接受客户端 config 自报的 user_id/workspace_ids——一旦宿主认证失效，
    # 那将成为跨工作区读取任意医学知识的通道（医疗产品授权降级必须 fail-closed）。
    raise ValueError("缺少 Aegra 认证上下文（langgraph_auth_user），拒绝执行")


def _require_uuid(value: object, field: str) -> str:
    raw = str(value or "").strip()
    try:
        return str(UUID(raw))
    except ValueError as err:
        raise ValueError(f"{field} 必须是合法 UUID，收到 {raw!r}") from err


def _request(state: AgentState, config: RunnableConfig) -> ChatRequest:
    """由 Aegra v2 输入（messages + configurable）构造领域请求。"""
    cf = config.get("configurable") or {}
    thread_id = _require_uuid(cf.get("thread_id"), "thread_id")
    identity, workspace_ids = _auth_context(cf)
    user_id = _require_uuid(identity, "user_id")
    if not workspace_ids:
        raise ValueError("缺少工作区上下文，拒绝执行医疗检索")
    workspace_id = _require_uuid(workspace_ids[0], "workspace_id")
    messages = state.get("messages") or []
    # 仅接受纯文本 content；多模态 content blocks（list）无法安全转为提问文本，按缺失处理
    question = next(
        (
            m.content
            for m in reversed(messages)
            if isinstance(m, HumanMessage) and isinstance(m.content, str) and m.content
        ),
        "",
    )
    if not question:
        raise ValueError("messages 中缺少 user 消息")
    return ChatRequest(
        question=str(question),
        conversation_id=thread_id,
        user_id=user_id,
        workspace_id=workspace_id,
        # Agent Protocol 的 JSON config：仅显式 true 视为深度分析（无字符串猜测）
        analysis_depth=cf.get("analysis_depth") is True,
    )


def _ai_message(result: ChatResult) -> AIMessage:
    evidence = [e.to_payload() for e in result.evidence]
    safety = result.safety.to_payload() if result.safety is not None else None
    return AIMessage(
        # 反馈（点赞/点踩）以落库消息 ID 为准；缺失时回退临时 ID（仅本轮 UI 展示可用）
        id=result.message_id or str(uuid4()),
        content=result.message,
        additional_kwargs={
            "custom": {
                "evidence": evidence,
                "safety": safety,
                "outcome": result.outcome.value,
            }
        },
    )


def build_graph(
    pipeline: ChatPipeline,
    *,
    gate=None,
    gate_limit: int = 10,
    gate_wait_s: float = 15.0,
) -> CompiledStateGraph:
    """构建受控编译图：单编排节点 + 官方 timeout / error_handler 默认。

    ``gate`` 为可选的跨进程并发闸；生产组合根传入 RedisConcurrencyGate 与额度/等待预算。
    """

    async def orchestrate(state: AgentState, config: RunnableConfig) -> dict[str, object]:
        request = _request(state, config)
        writer = get_stream_writer()
        holder: str | None = None
        if gate is not None:
            holder = f"{request.user_id}:{request.conversation_id}"
            granted = await gate.acquire(
                "chat", limit=gate_limit, holder=holder, wait_s=gate_wait_s
            )
            if not granted:
                return {"messages": [_degraded_ai(_BUSY_MESSAGE)], "evidence": []}
        try:
            result: ChatResult | None = None
            async for event in pipeline.run_stream(
                request, trace_id=(config.get("configurable") or {}).get("thread_id")
            ):
                if isinstance(event, AnalysisEvent):
                    writer({"stage": "analysis", **event.to_payload()})
                elif isinstance(event, EvidenceEvent):
                    writer({"stage": "evidence", **event.to_payload()})
                elif isinstance(event, SafetyEvent):
                    writer({"stage": "safety", **event.to_payload()})
                elif isinstance(event, TokenEvent):
                    writer({"stage": "token", "tokens": event.text})
                elif isinstance(event, DoneEvent):
                    result = event.result
        finally:
            if gate is not None and holder is not None:
                await gate.release("chat", holder)
        if result is None:
            # 编排不变量失败；RuntimeError 不在 default_retry_on 内（故意不重试）
            raise RuntimeError("编排流水线未产出结束事件")
        ai = _ai_message(result)
        return {
            "messages": [ai],
            "evidence": [e.to_payload() for e in result.evidence],
        }

    def on_error(state: AgentState, error: NodeError) -> Command:
        """官方 error_handler：节点失败后写入安全降级 AIMessage，避免裸异常冒泡。

        请求上下文非法（ValueError：缺工作区、身份非法、缺 user 消息）属客户端/配置问题，
        给出可诊断文案并记录原始异常；依赖故障统一按“服务不可用”降级，且不计入重试。
        """
        if isinstance(error.error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            raise error.error
        invalid_request = isinstance(error.error, ValueError)
        if isinstance(error.error, ConversationBusyError):
            # 提交幂等：同一会话已有进行中 Run——明确告知用户而非归为故障
            writer = get_stream_writer()
            writer({"stage": "error", "message": _BUSY_MESSAGE, "error": "conversation_busy"})
            return Command(update={"messages": [_degraded_ai(_BUSY_MESSAGE)], "evidence": []})
        message = _INVALID_REQUEST_MESSAGE if invalid_request else _FAILURE_MESSAGE
        logger.opt(exception=error.error).error(
            "会话编排节点执行失败（请求参数校验失败={}）：error_type={}",
            invalid_request,
            type(error.error).__name__,
        )
        writer = get_stream_writer()
        writer({"stage": "error", "message": message, "error": type(error.error).__name__})
        return Command(update={"messages": [_degraded_ai(message)], "evidence": []})

    builder = StateGraph(AgentState)
    # timeout 仅挂在 async 编排节点上（官方限制：sync error_handler 不能带 timeout）。
    # run_timeout 为硬上限；idle_timeout 在节点有进度信号（custom 流写入）时自动续期，
    # 避免“持续输出 token 但总时长超过硬上限”的长回答被误杀。
    builder.add_node(
        "orchestrate",
        orchestrate,
        timeout=TimeoutPolicy(run_timeout=300.0, idle_timeout=90.0),
        # pyright 未完全建模 NodeError 注入签名；官方文档支持 (state, error: NodeError)
        error_handler=on_error,  # type: ignore[arg-type]
    )
    builder.add_edge(START, "orchestrate")
    builder.add_edge("orchestrate", END)
    return builder.compile()
