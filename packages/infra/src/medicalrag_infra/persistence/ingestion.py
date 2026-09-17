"""文档摄取运行持久化仓储适配器：实现 medical_core.ingestion.ports.IngestionRunRepository 协议端口。

阶段完成记录采用数据库唯一索引（UNIQUE(run_id, stage)）保障幂等性：当重试已完成的阶段时作为空操作安全返回；
状态流转严格遵循单向前进原则，处于终止状态或阶段错位时抛出 InvalidIngestionTransition 异常。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.ingestion.knowledge import Document
from medicalrag_core.ingestion.state_machine import (
    IngestionRunState,
    InvalidIngestionTransition,
    advance,
    is_terminal,
)

from .models import DocumentRow, IngestionRun, IngestionRunStage, OutboxRow


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

    async def enqueue_upload(
        self,
        document: Document,
        metadata: Mapping[str, object],
        *,
        event_type: str,
        payload: Mapping[str, object],
    ) -> str:
        """单事务写入 Document、IngestionRun（含元数据）与 Outbox 事件，返回 run_id。

        Outbox 模式要求事件与业务状态**同一事务**提交；分多次 commit 会在进程崩溃时
        留下永远停在 ACCEPTED、没有任何后台事件可投递的孤儿文档。
        事件的 aggregate_id 固定为该 Run 的 id（Relay 据此推进业务阶段），由仓储自行赋值，
        避免调用方拿到尚未生成的 run_id。
        """
        async with self._sessions() as session:
            session.add(
                DocumentRow(
                    id=uuid.UUID(document.id),
                    knowledge_base_id=uuid.UUID(document.knowledge_base_id),
                    workspace_id=uuid.UUID(document.workspace_id),
                    title=document.title,
                    format=document.format,
                    size_bytes=document.size_bytes,
                    ingestion_state=document.ingestion_state.value,
                )
            )
            run = IngestionRun(
                document_id=uuid.UUID(document.id),
                workspace_id=uuid.UUID(document.workspace_id),
                state=IngestionRunState.ACCEPTED.value,
                data=dict(metadata),
            )
            session.add(run)
            await session.flush()  # 取得 run.id（主键由 Python 侧 uuid7 生成）
            session.add(
                OutboxRow(
                    aggregate_type="ingestion_run",
                    aggregate_id=str(run.id),
                    event_type=event_type,
                    payload=dict(payload),
                )
            )
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

    async def all_metadata(self) -> list[dict[str, object]]:
        """全量 Run 元数据（对象存储孤儿对账使用：收集 object_key / artifact_ref / vectors_ref 引用集）。"""
        async with self._sessions() as session:
            rows = (await session.scalars(select(IngestionRun))).all()
            return [dict(row.data or {}) for row in rows]

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

    async def mark_failed(self, run_id: str, reason: str) -> None:
        """将 Run 置为 FAILED 终止态（重试耗尽后的终局标记）；已处于终止态时幂等空操作。

        失败原因与失败发生时所处的阶段写入 ``run.data``（failure_reason / failed_stage），
        供运营台展示与重放续跑定位。
        """
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            if is_terminal(IngestionRunState(run.state)):
                return
            data = dict(run.data or {})
            data["failure_reason"] = reason
            data["failed_stage"] = run.state
            run.data = data
            run.state = IngestionRunState.FAILED.value
            await session.commit()

    async def resume_failed(self, run_id: str, stage: IngestionRunState) -> bool:
        """将 FAILED Run 复位到其失败阶段以支持重放续跑（条件更新，CAS 语义）。

        仅当当前状态为 FAILED 且失败阶段与请求阶段一致时才复位；返回是否发生复位。
        失败阶段本身尚未记入阶段表，复位后重跑该阶段即可继续向后推进。
        """
        async with self._sessions() as session:
            run = await self._get(session, run_id)
            if IngestionRunState(run.state) is not IngestionRunState.FAILED:
                return False
            if str((run.data or {}).get("failed_stage", "")) != stage.value:
                return False
            run.state = stage.value
            await session.commit()
            return True

    async def fail_stale_runs(self, *, max_age_s: int, reason: str = "stale_timeout") -> int:
        """僵尸 Run 自愈：将长时间停滞在非终态的 Run 置为 FAILED，返回处理数量。

        活跃 Run 每完成一个阶段、写入元数据（含长阶段内部的轮询/逐切片心跳）都会刷新 updated_at，
        因此 ``updated_at`` 早于阈值的**非终态** Run 即可判定为进程崩溃等事故留下的停滞状态
        （终态过滤在 SQL 端完成，不把已终结的 Run 拉回应用层再丢弃）。
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_s)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(IngestionRun).where(
                        IngestionRun.updated_at < cutoff,
                        IngestionRun.state.notin_(
                            [IngestionRunState.PUBLISHED.value, IngestionRunState.FAILED.value]
                        ),
                    )
                )
            ).all()
            for run in rows:
                data = dict(run.data or {})
                data["failure_reason"] = reason
                data["failed_stage"] = run.state
                run.data = data
                run.state = IngestionRunState.FAILED.value
            if rows:
                await session.commit()
            return len(rows)

    @staticmethod
    async def _get(session: AsyncSession, run_id: str) -> IngestionRun:
        run = await session.get(IngestionRun, uuid.UUID(run_id))
        if run is None:
            raise KeyError(f"摄取运行记录不存在: {run_id}")
        return run
