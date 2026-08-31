"""聊天 Run 状态机（架构文档 Chat State Machine）。

对单次 Agent Run 建模为单向递进、具备明确终止态的状态机契约。每个终止态均会持久化：
一条用户输入消息、一条助手响应或错误事件，以及对应的业务 Run 完成记录。
相较于架构状态图，此处补充了 SAFETY 状态：表示 PROHIBITED（个体化临床决策）请求在检索前触发安全短路（ADR 0043）。
"""

from __future__ import annotations

import enum


class ChatRunState(enum.StrEnum):
    """Run 所处的当前执行阶段（对应架构状态图）。"""

    ACCEPTED = "accepted"
    MEMORY_LOADED = "memory_loaded"
    ANALYZED = "analyzed"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    GUIDANCE = "guidance"
    SYSTEM_ONLY = "system_only"
    SAFETY = "safety"
    EMPTY = "empty"
    FALLBACK = "fallback"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatRunEvent(enum.StrEnum):
    """驱动 Run 状态单向迁移的可观测事件。"""

    MEMORY_LOADED = "memory_loaded"
    ANALYZED = "analyzed"
    ROUTE_GUIDANCE = "route_guidance"
    ROUTE_SYSTEM_ONLY = "route_system_only"
    ROUTE_SAFETY = "route_safety"
    ROUTE_RETRIEVAL = "route_retrieval"
    NO_EVIDENCE = "no_evidence"
    EVIDENCE_FOUND = "evidence_found"
    MODEL_COMPLETED = "model_completed"
    PROVIDER_FAILURE = "provider_failure"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidChatRunTransition(ValueError):
    """当事件在 Run 的当前状态下不合法时抛出该异常。"""


TERMINAL_STATES = frozenset({ChatRunState.COMPLETED, ChatRunState.FAILED, ChatRunState.CANCELLED})

_TRANSITIONS: dict[tuple[ChatRunState, ChatRunEvent], ChatRunState] = {
    # 基础前置阶段：ACCEPTED -> MEMORY_LOADED -> ANALYZED
    (ChatRunState.ACCEPTED, ChatRunEvent.MEMORY_LOADED): ChatRunState.MEMORY_LOADED,
    (ChatRunState.MEMORY_LOADED, ChatRunEvent.ANALYZED): ChatRunState.ANALYZED,
    # 意图分析完成后的路由分发分支
    (ChatRunState.ANALYZED, ChatRunEvent.ROUTE_GUIDANCE): ChatRunState.GUIDANCE,
    (ChatRunState.ANALYZED, ChatRunEvent.ROUTE_SYSTEM_ONLY): ChatRunState.SYSTEM_ONLY,
    (ChatRunState.ANALYZED, ChatRunEvent.ROUTE_SAFETY): ChatRunState.SAFETY,
    (ChatRunState.ANALYZED, ChatRunEvent.ROUTE_RETRIEVAL): ChatRunState.RETRIEVING,
    # 检索执行结果分支
    (ChatRunState.RETRIEVING, ChatRunEvent.NO_EVIDENCE): ChatRunState.EMPTY,
    (ChatRunState.RETRIEVING, ChatRunEvent.EVIDENCE_FOUND): ChatRunState.GENERATING,
    # 模型生成结果分支
    (ChatRunState.GENERATING, ChatRunEvent.MODEL_COMPLETED): ChatRunState.COMPLETED,
    (ChatRunState.GENERATING, ChatRunEvent.PROVIDER_FAILURE): ChatRunState.FALLBACK,
    # 短路分支收敛为 COMPLETED 终止态
    (ChatRunState.GUIDANCE, ChatRunEvent.COMPLETE): ChatRunState.COMPLETED,
    (ChatRunState.SYSTEM_ONLY, ChatRunEvent.COMPLETE): ChatRunState.COMPLETED,
    (ChatRunState.SAFETY, ChatRunEvent.COMPLETE): ChatRunState.COMPLETED,
    (ChatRunState.EMPTY, ChatRunEvent.COMPLETE): ChatRunState.COMPLETED,
    (ChatRunState.FALLBACK, ChatRunEvent.COMPLETE): ChatRunState.COMPLETED,
    # 异常与取消终止分支
    (ChatRunState.ACCEPTED, ChatRunEvent.FAILED): ChatRunState.FAILED,
    (ChatRunState.MEMORY_LOADED, ChatRunEvent.CANCELLED): ChatRunState.CANCELLED,
    (ChatRunState.GENERATING, ChatRunEvent.CANCELLED): ChatRunState.CANCELLED,
}


def transition(current: ChatRunState, event: ChatRunEvent) -> ChatRunState:
    """计算在当前状态 `current` 下发生事件 `event` 时迁移的目标状态。

    对于状态机未定义的不合法迁移，直接抛出 InvalidChatRunTransition 异常；调用方严禁伪造迁移路径。
    """
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise InvalidChatRunTransition(current, event) from None


def is_terminal(state: ChatRunState) -> bool:
    """判定给定状态 `state` 是否为 Run 终止态（COMPLETED / FAILED / CANCELLED）。"""
    return state in TERMINAL_STATES
