"""医疗知识聊天 API 路由（POST /api/chat；提供会话鉴权 + ChatPipeline 确定性编排 + 结构化响应结果）。"""

from __future__ import annotations

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from medicalrag_core.chat.model import ChatRequest as DomainChatRequest
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.evidence import Evidence

from ..deps import UserCtx

router = APIRouter(prefix="/api/chat")


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
    """聊天限流统一拦截：非流式与流式端点共用同一令牌桶（保障 429 频控语义严格一致）。"""
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


class ChatRequestIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str
    analysis_depth: bool = False


class EvidenceOut(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    snippet: str
    citation_label: str
    score: float


class ChatResponse(BaseModel):
    outcome: str
    message: str
    run_id: str
    evidence: list[EvidenceOut] = []
    safety_notice: str | None = None
    safety_escalation: str | None = None


def _evidence_out(evidence: tuple[Evidence, ...]) -> list[EvidenceOut]:
    # 证据载荷序列化单一来源：严格复用领域层 Evidence.to_payload（ADR 0080）
    return [EvidenceOut(**e.to_payload()) for e in evidence]  # type: ignore[arg-type]


@router.post("")
async def chat(
    body: ChatRequestIn,
    request: Request,
    ctx: UserCtx,
    pipeline: Annotated[ChatPipeline, Depends(_pipeline)],
) -> ChatResponse:
    """非流式同步医疗问答端点：执行完整的 8 步编排管线并返回结构化回答与溯源证据。"""
    await _acquire_chat_slot(request, ctx)
    result = await pipeline.run(_domain_request(body, ctx))
    safety = result.safety
    return ChatResponse(
        outcome=result.outcome.value,
        message=result.message,
        run_id=result.run_id,
        evidence=_evidence_out(result.evidence),
        safety_notice=safety.scope_notice if safety is not None else None,
        safety_escalation=safety.escalation if safety is not None else None,
    )
