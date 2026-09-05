"""流式聊天 API 路由（POST /api/chat/stream；原生流式直出，无阻塞等待）。

基于 FastAPI 内置 EventSourceResponse（版本基线门禁：禁止手写 StreamingResponse）
流式产出编排流水线的类型化事件（意图分析、检索证据、安全评估、Token 增量、执行结束）。

定位：本地开发调试与快速验证路径；生产聊天前端经由 Aegra Agent Protocol v2 运行时
（/api/agent，浏览器官方 useStreamRuntime + LangGraph messages/custom 通道）消费。
统一使用 UserCtx 依赖完成身份鉴权；事件载荷序列化统一复用领域层定义的 `to_payload()` 接口。
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import EventSourceResponse
from fastapi.sse import format_sse_event
from pydantic import BaseModel, Field

from medicalrag_core.chat.pipeline import ChatPipeline

from ..deps import UserCtx
from .chat import _acquire_chat_slot, _domain_request, _pipeline

router = APIRouter(prefix="/api/chat")


class StreamIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str
    analysis_depth: bool = False


@router.post("/stream")
async def chat_stream(
    body: StreamIn,
    request: Request,
    ctx: UserCtx,
    pipeline: Annotated[ChatPipeline, Depends(_pipeline)],
) -> EventSourceResponse:
    """流式医疗问答端点：通过 SSE 实时向客户端推送意图分析、检索证据、安全评估及 Token 生成流。"""
    await _acquire_chat_slot(request, ctx)
    domain = _domain_request(body, ctx)

    async def gen():
        async for event in pipeline.run_stream(domain):
            yield format_sse_event(
                data_str=json.dumps(event.to_payload(), ensure_ascii=False),
                event=event.sse_name,
            )

    return EventSourceResponse(gen())
