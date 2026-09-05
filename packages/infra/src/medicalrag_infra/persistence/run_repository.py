"""聊天运行持久化仓储适配器：实现 medical_core.chat.ports.RunRepository 协议端口。

ChatRun 记录为聊天业务执行状态的唯一事实来源；外部观测系统的 trace_id 仅用于链路追踪关联。
所有业务 ID 严格按照 uuid7 规范在信任边界校验并解析。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.model import ChatRequest, ChatResult
from medicalrag_core.chat.run_state import ChatRunState

from .models import ChatRun, RunEvent


class SqlRunRepository:
    """基于 SQLAlchemy 异步会话实现的聊天运行事实记录仓储适配器。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create_run(self, request: ChatRequest) -> str:
        """根据聊天请求创建一条处于 ACCEPTED 初始状态的 ChatRun 记录，并返回该运行的字符串 ID。"""
        async with self._sessions() as session:
            run = ChatRun(
                conversation_id=uuid.UUID(request.conversation_id),
                user_id=uuid.UUID(request.user_id),
                workspace_id=uuid.UUID(request.workspace_id),
                status=ChatRunState.ACCEPTED.value,
            )
            session.add(run)
            await session.commit()
            return str(run.id)

    async def record_state(self, run_id: str, state: ChatRunState) -> None:
        """记录状态迁移事件并更新 ChatRun 记录的当前状态。"""
        async with self._sessions() as session:
            run = await session.get(ChatRun, uuid.UUID(run_id))
            if run is None:
                raise KeyError(f"聊天运行记录不存在: {run_id}")
            run.status = state.value
            session.add(RunEvent(run_id=run.id, event=state.value))
            await session.commit()

    async def complete(self, run_id: str, result: ChatResult) -> None:
        """完成聊天运行：记录最终回复内容、执行结果类型、策略版本及链路追踪标识，并标记完成时间。"""
        async with self._sessions() as session:
            run = await session.get(ChatRun, uuid.UUID(run_id))
            if run is None:
                raise KeyError(f"聊天运行记录不存在: {run_id}")
            run.status = ChatRunState.COMPLETED.value
            run.outcome = result.outcome.value
            run.assistant_message = result.message
            run.retrieval_policy_version = result.retrieval_policy_version
            run.trace_id = result.trace_id
            run.completed_at = datetime.now(UTC)
            await session.commit()
