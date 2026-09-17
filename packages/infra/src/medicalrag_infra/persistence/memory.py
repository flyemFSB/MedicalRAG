"""会话记忆持久化适配器：实现 medical_core.chat.ports.Memory 协议端口。

按时间正序加载指定会话的有界最近历史消息窗口；溢出窗口的早期消息由后台摘要管线
增量压缩为会话级摘要（``conversations.summary``，水位 ``summary_offset``），
加载时以 system 消息形式置于窗口之前，兼顾长程上下文与 Token 成本。
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.model import (
    ChatRequest,
    MemoryContext,
    MessageRole,
)
from medicalrag_core.chat.model import (
    Message as DomainMessage,
)
from medicalrag_core.chat.ports import ConversationSummarizer
from medicalrag_core.ids import uuid7
from medicalrag_infra.logging import logger

from .models import ConversationRow
from .models import Message as MessageRow

# 摘要触发条件：溢出窗口的未摘要消息数达到该阈值时执行一次压缩
_SUMMARY_EVERY = 10
# 单条消息进入摘要文本的最大长度（防超长消息撑爆摘要输入）
_TRANSCRIPT_ITEM_CAP = 500


class SqlMemory:
    """基于 SQLAlchemy 异步会话实现的会话记忆仓储适配器（含后台摘要压缩）。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        window: int = 20,
        summarizer: ConversationSummarizer | None = None,
    ) -> None:
        self._sessions = session_factory
        self._window = window
        self._summarizer = summarizer
        # 持有强引用防止后台任务被 GC；完成即移除
        self._summary_tasks: set[asyncio.Task[None]] = set()

    async def load(self, request: ChatRequest) -> MemoryContext:
        """加载会话摘要与最近消息窗口（摘要以 system 消息置于首位，消息按时间由旧到新正序）。"""
        conversation_id = uuid.UUID(request.conversation_id)
        workspace_id = uuid.UUID(request.workspace_id)
        async with self._sessions() as session:
            summary_row = (
                await session.execute(
                    select(ConversationRow.summary).where(ConversationRow.id == conversation_id)
                )
            ).one_or_none()
            summary = summary_row[0] if summary_row is not None else None
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
        messages: list[DomainMessage] = []
        if summary:
            messages.append(DomainMessage(role=MessageRole.SYSTEM, text=f"此前对话摘要：{summary}"))
        messages.extend(
            DomainMessage(role=MessageRole(row.role), text=row.text) for row in reversed(rows)
        )
        return MemoryContext(messages=tuple(messages))

    async def append(self, request: ChatRequest, message: DomainMessage) -> str | None:
        """向会话历史追加一条新消息，返回落库消息 ID；助手消息写入后异步触发摘要压缩。"""
        message_id = uuid7()
        async with self._sessions() as session:
            session.add(
                MessageRow(
                    id=message_id,
                    conversation_id=uuid.UUID(request.conversation_id),
                    user_id=uuid.UUID(request.user_id),
                    workspace_id=uuid.UUID(request.workspace_id),
                    role=message.role.value,
                    text=message.text,
                )
            )
            await session.commit()
        if message.role is MessageRole.ASSISTANT and self._summarizer is not None:
            self._schedule_summary(request)
        return str(message_id)

    def _schedule_summary(self, request: ChatRequest) -> None:
        task = asyncio.create_task(self._summarize_if_needed(request))
        self._summary_tasks.add(task)
        task.add_done_callback(self._summary_tasks.discard)

    async def _summarize_if_needed(self, request: ChatRequest) -> None:
        """增量摘要压缩：把溢出窗口且未被摘要覆盖的早期消息交给摘要模型，写回会话摘要与水位。

        后台 fire-and-forget：失败仅记日志，不影响本次回答（下次 append 重新触发）。
        """
        assert self._summarizer is not None
        conversation_id = uuid.UUID(request.conversation_id)
        try:
            async with self._sessions() as session:
                conversation = await session.get(ConversationRow, conversation_id)
                if conversation is None:
                    return
                offset = conversation.summary_offset
                total = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(MessageRow)
                        .where(MessageRow.conversation_id == conversation_id)
                    )
                    or 0
                )
                end = total - self._window  # 窗口内消息保持原文，不进入摘要
                if end - offset < _SUMMARY_EVERY:
                    return
                rows = (
                    await session.scalars(
                        select(MessageRow)
                        .where(MessageRow.conversation_id == conversation_id)
                        .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
                        .offset(total - end)
                        .limit(end - offset)
                    )
                ).all()
                transcript = "\n".join(
                    f"{row.role}: {row.text[:_TRANSCRIPT_ITEM_CAP]}" for row in reversed(rows)
                )
            summary = await self._summarizer.summarize(transcript)
            if not summary:
                return
            async with self._sessions() as session:
                conversation = await session.get(ConversationRow, conversation_id)
                if conversation is None or conversation.summary_offset != offset:
                    return  # 并发摘要：水位已推进，放弃本次（下一次会覆盖剩余部分）
                conversation.summary = summary[:1000]
                conversation.summary_offset = end
                await session.commit()
        except Exception:
            logger.exception("会话摘要压缩生成失败（不影响本次问答交互）：conversation_id={}", conversation_id)
            # ponytail: 摘要失败无重试，依赖下次 append 重新触发；需保证收敛时再加退避重试

    async def aclose(self) -> None:
        """停机时回收在途的后台摘要任务（规范 §1.4：后台任务必须有创建者与关闭路径）。"""
        pending = [task for task in self._summary_tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
