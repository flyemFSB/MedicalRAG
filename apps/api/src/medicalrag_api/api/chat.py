"""聊天路由共享依赖（chat.py / chat_stream.py 的公共装配与请求映射）。

生产聊天路径为 Aegra Agent Protocol v2（/api/agent，浏览器官方 useStreamRuntime）；
/api/chat/stream 仅保留为本地开发调试路径。非流式 POST /api/chat 已移除，契约产物随之重新导出。
"""

from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException, Request

from medicalrag_core.chat.model import ChatRequest as DomainChatRequest
from medicalrag_core.chat.pipeline import ChatPipeline

from ..deps import UserCtx


class _ChatRequestBody(Protocol):
    """Chat 与 ChatStream 请求体共享的鸭子类型契约。"""

    question: str
    conversation_id: str
    analysis_depth: bool


async def _pipeline(request: Request) -> ChatPipeline:
    """在用户首次发起聊天时延迟初始化并缓存编排流水线（将外部 Provider 连通开销延迟至实际需要时）。"""
    pipeline = request.app.state.chat
    if pipeline is None:
        pipeline = await request.app.state.build_chat()
        request.app.state.chat = pipeline
    return pipeline


async def _acquire_chat_slot(request: Request, ctx: UserCtx) -> None:
    """聊天限流统一拦截：流式端点专用令牌桶（保障 429 频控语义严格一致）。"""
    settings = request.app.state.settings
    allowed = await request.app.state.rate_limiter.acquire(
        f"chat:{ctx.user_id}",
        limit=settings.chat_rate_limit,
        window_s=settings.chat_rate_window_s,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    request.app.state.metrics.inc("chat_requests_total")


def _domain_request(body: _ChatRequestBody, ctx: UserCtx) -> DomainChatRequest:
    """将 API 请求体映射为领域层 ChatRequest 实体。"""
    return DomainChatRequest(
        question=body.question,
        conversation_id=body.conversation_id,
        user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        analysis_depth=body.analysis_depth,
    )
