"""会话 / 反馈 / Run 列表持久化仓储（自 operator.py 按领域聚合拆分；组合门面见 operator.py）。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.records import Conversation, Feedback, FeedbackValue

from .models import (
    ChatRun,
    ConversationRow,
    DocumentRow,
    FeedbackRow,
    IngestionRun,
    Message,
    _iso,
)


def _conversation_from_row(row: ConversationRow) -> Conversation:
    return Conversation(
        id=str(row.id),
        user_id=str(row.user_id),
        workspace_id=str(row.workspace_id),
        title=row.title,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


class SqlConversationRepository:
    """业务会话持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sessions() as session:
            row = ConversationRow(
                id=uuid.UUID(conversation.id),
                user_id=uuid.UUID(conversation.user_id),
                workspace_id=uuid.UUID(conversation.workspace_id),
                title=conversation.title,
            )
            session.add(row)
            await session.commit()
            return _conversation_from_row(row)

    async def list_for_user(self, user_id: str) -> tuple[Conversation, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ConversationRow)
                    .where(ConversationRow.user_id == uuid.UUID(user_id))
                    .order_by(ConversationRow.updated_at.desc())
                )
            ).all()
            return tuple(_conversation_from_row(r) for r in rows)

    async def owned_by(self, conversation_id: str, user_id: str) -> bool:
        """校验会话归属：非法 ID 或不属于该用户时返回 False（供写路径做对象级鉴权）。"""
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return False
        async with self._sessions() as session:
            found = await session.scalar(
                select(func.count())
                .select_from(ConversationRow)
                .where(
                    ConversationRow.id == conversation_uuid,
                    ConversationRow.user_id == user_uuid,
                )
            )
            return bool(found)


class SqlFeedbackRepository:
    """用户反馈持久化仓储：实现 FeedbackRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def submit(self, feedback: Feedback) -> None:
        async with self._sessions() as session:
            session.add(
                FeedbackRow(
                    id=uuid.UUID(feedback.id),
                    message_id=uuid.UUID(feedback.message_id),
                    conversation_id=uuid.UUID(feedback.conversation_id),
                    user_id=uuid.UUID(feedback.user_id),
                    workspace_id=uuid.UUID(feedback.workspace_id),
                    value=feedback.value.value,
                    comment=feedback.comment,
                )
            )
            await session.commit()

    async def list_all(self) -> tuple[Feedback, ...]:
        """全平台反馈列表（operator 数据面语义）。"""
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(FeedbackRow).order_by(FeedbackRow.created_at.desc()))
            ).all()
            return tuple(
                Feedback(
                    id=str(r.id),
                    message_id=str(r.message_id),
                    conversation_id=str(r.conversation_id),
                    user_id=str(r.user_id),
                    workspace_id=str(r.workspace_id),
                    value=FeedbackValue(r.value),
                    comment=r.comment,
                    created_at=str(r.created_at),
                )
                for r in rows
            )


class SqlRunListingRepository:
    """聊天运行记录追踪与管理看板聚合查询仓储（跨 chat_runs / messages / conversations 表进行只读查询）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def recent_runs(self, limit: int = 50) -> tuple[ChatRun, ...]:
        """列出最近的聊天运行（operator 平台级全量）。"""
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ChatRun).order_by(ChatRun.created_at.desc()).limit(limit)
                )
            ).all()
            return tuple(rows)

    async def get_run(self, run_id: str) -> ChatRun | None:
        """按主键获取单条运行记录（追踪详情；全平台语义，避免全量拉取后线性查找）。"""
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return None
        async with self._sessions() as session:
            return await session.get(ChatRun, run_uuid)

    async def question_count(self) -> int:
        async with self._sessions() as session:
            query = select(func.count()).select_from(Message).where(Message.role == "user")
            return int(await session.scalar(query) or 0)

    async def conversation_count(self) -> int:
        async with self._sessions() as session:
            query = select(func.count()).select_from(ConversationRow)
            return int(await session.scalar(query) or 0)

    async def avg_latency_ms(self) -> float:
        async with self._sessions() as session:
            # 数据库端聚合平均时延（秒级精度），不把全部运行行拉回 Python 计算
            query = select(
                func.avg(
                    (
                        func.extract("epoch", ChatRun.completed_at)
                        - func.extract("epoch", ChatRun.created_at)
                    )
                    * 1000
                )
            ).where(ChatRun.completed_at.is_not(None))
            latency = await session.scalar(query)
            return round(float(latency), 1) if latency is not None else 0.0

    async def published_docs(self) -> int:
        async with self._sessions() as session:
            query = (
                select(func.count())
                .select_from(DocumentRow)
                .where(DocumentRow.ingestion_state == IngestionRunState.PUBLISHED.value)
            )
            return int(await session.scalar(query) or 0)

    async def failed_runs(self) -> int:
        async with self._sessions() as session:
            query = (
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.state == IngestionRunState.FAILED.value)
            )
            return int(await session.scalar(query) or 0)
