"""聊天 Run 状态机（架构文档 Chat State Machine）。

对单次 Agent Run 建模为单向递进、具备明确终止态的状态机契约。
FAILED / CANCELLED 为终止态，由编排器在异常路径直接落库（不经 transition 校验：
异常路径以可靠落库优先，编排器保证绝不把已完成的 Run 改写为失败态）。
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


class InvalidChatRunTransition(ValueError):
    """当事件在 Run 的当前状态下不合法时抛出该异常。"""


_TRANSITIONS: dict[tuple[ChatRunState, ChatRunEvent], ChatRunState] = {
    # 基础前置阶段：ACCEPTED -> MEMORY_LOADED -> ANALYZED
    (ChatRunState.ACCEPTED, ChatRunEvent.MEMORY_LOADED): ChatRunState.MEMORY_LOADED,
    (ChatRunState.MEMORY_LOADED, ChatRunEvent.ANALYZED): ChatRunState.ANALYZED,
    # 确定性违规前置拦截：不经过外部模型分类，直接从记忆加载后短路（ADR 0043）
    (ChatRunState.MEMORY_LOADED, ChatRunEvent.ROUTE_SAFETY): ChatRunState.SAFETY,
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
}


def transition(current: ChatRunState, event: ChatRunEvent) -> ChatRunState:
    """计算在当前状态 `current` 下发生事件 `event` 时迁移的目标状态。

    对于状态机未定义的不合法迁移，直接抛出 InvalidChatRunTransition 异常；调用方严禁伪造迁移路径。
    """
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise InvalidChatRunTransition(current, event) from None
