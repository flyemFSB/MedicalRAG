"""文档摄取运行持久化仓储适配器：实现 medical_core.ingestion.ports.IngestionRunRepository 协议端口。

阶段完成记录采用数据库唯一索引（UNIQUE(run_id, stage)）保障幂等性：当重试已完成的阶段时作为空操作安全返回；
状态流转严格遵循单向前进原则，处于终止状态或阶段错位时抛出 InvalidIngestionTransition 异常。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.ingestion.state_machine import (
    IngestionRunState,
    InvalidIngestionTransition,
    advance,
    is_terminal,
)

from .models import IngestionRun, IngestionRunStage


class SqlIngestionRunRepository:
    """基于 SQLAlchemy 异步会话实现的文档摄取运行持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create_run(self, document_id: str, workspace_id: str) -> str:
        async with self._sessions() as session:
            run = IngestionRun(
                document_id=uuid.UUID(document_id),
                workspace_id=uuid.UUID(workspace_id),
                state=IngestionRunState.ACCEPTED.value,
            )
            session.add(run)
            await session.commit()
            return str(run.id)

    async def state(self, run_id: str) -> IngestionRunState:
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            return IngestionRunState(run.state)

    async def set_metadata(self, run_id: str, key: str, value: object) -> None:
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            data = dict(run.data or {})
            data[key] = value
            run.data = data
            await session.commit()

    async def metadata(self, run_id: str) -> dict[str, object]:
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            return dict(run.data or {})

    async def complete_stage(self, run_id: str, stage: IngestionRunState) -> IngestionRunState:
        """幂等完成指定的摄取阶段 `stage` 并向前推进状态；返回流转后的新状态。

        若阶段已处于完成状态（包括历史阶段重试），则作为幂等空操作直接返回当前状态；
        若处于终止状态或存在阶段错位，则抛出异常。
        """
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            current = IngestionRunState(run.state)
            if is_terminal(current):
                raise InvalidIngestionTransition(current)
            already = await session.scalar(
                select(IngestionRunStage).where(
                    IngestionRunStage.run_id == run.id,
                    IngestionRunStage.stage == stage.value,
                )
            )
            if already is not None:
                return current
            if stage is not current:
                raise InvalidIngestionTransition(
                    f"摄取阶段错位: 目标阶段 {stage} != 当前阶段 {current}"
                )
            session.add(IngestionRunStage(run_id=run.id, stage=stage.value))
            try:
                await session.flush()
            except IntegrityError:
                # 并发重复完成处理：触发数据库 UNIQUE 约束时回滚并作为幂等空操作返回
                await session.rollback()
                return current
            new_state = advance(stage)
            run.state = new_state.value
            await session.commit()
            return new_state

    @staticmethod
    async def _get(session: AsyncSession, run_id: str) -> IngestionRun:
        run = await session.get(IngestionRun, uuid.UUID(run_id))
        if run is None:
            raise KeyError(f"摄取运行记录不存在: {run_id}")
        return run
