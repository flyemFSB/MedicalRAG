"""会话记忆持久化适配器：实现 medical_core.chat.ports.Memory 协议端口。

按时间正序加载指定会话的有界最近历史消息窗口（规范：加载固定长度的最近窗口）；
更早轮次的摘要由对话摘要管线异步处理。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.model import (
    ChatRequest,
    MemoryContext,
    MessageRole,
)
from medicalrag_core.chat.model import (
    Message as DomainMessage,
)

from .models import Message as MessageRow


class SqlMemory:
    """基于 SQLAlchemy 异步会话实现的会话记忆仓储适配器。"""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, window: int = 20
    ) -> None:
        self._sessions = session_factory
        self._window = window

    async def load(self, request: ChatRequest) -> MemoryContext:
        """加载该会话在指定授权工作区（Workspace）下的最近消息窗口列表（按时间由旧到新正序排列）。"""
        conversation_id = uuid.UUID(request.conversation_id)
        workspace_id = uuid.UUID(request.workspace_id)
        async with self._sessions() as session:
            result = await session.execute(
                select(MessageRow)
                .where(
                    MessageRow.conversation_id == conversation_id,
                    MessageRow.workspace_id == workspace_id,
                )
                .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
                .limit(self._window)
            )
            rows = list(result.scalars().all())
        messages = tuple(
            DomainMessage(role=MessageRole(row.role), text=row.text) for row in reversed(rows)
        )
        return MemoryContext(messages=messages)

    async def append(self, request: ChatRequest, message: DomainMessage) -> None:
        """向会话历史追加一条新消息。"""
        async with self._sessions() as session:
            session.add(
                MessageRow(
                    conversation_id=uuid.UUID(request.conversation_id),
                    user_id=uuid.UUID(request.user_id),
                    workspace_id=uuid.UUID(request.workspace_id),
                    role=message.role.value,
                    text=message.text,
                )
            )
            await session.commit()
