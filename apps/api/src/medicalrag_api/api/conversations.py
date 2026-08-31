"""业务会话管理 API 路由（对应产品规范用户故事 16：支持多会话独立管理与病历上下文隔离）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from medicalrag_core.conversation import Conversation

from ..deps import UserCtx

router = APIRouter(prefix="/api/conversations")


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None


class ConversationIn(BaseModel):
    title: str = Field(default="新会话", max_length=255)


@router.get("")
async def list_conversations(ctx: UserCtx, request: Request) -> list[ConversationOut]:
    """查询当前登录用户的历史会话列表。"""
    rows = await request.app.state.operator.conversations.list_for_user(ctx.user_id)
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.post("", status_code=201)
async def create_conversation(
    body: ConversationIn, ctx: UserCtx, request: Request
) -> ConversationOut:
    """创建新的独立问答业务会话。"""
    created = await request.app.state.operator.conversations.create(
        Conversation(
            id=str(uuid.uuid7()),
            user_id=ctx.user_id,
            workspace_id=ctx.workspace_id,
            title=body.title,
        )
    )
    return ConversationOut(
        id=created.id,
        title=created.title,
        created_at=created.created_at,
        updated_at=created.updated_at,
    )
