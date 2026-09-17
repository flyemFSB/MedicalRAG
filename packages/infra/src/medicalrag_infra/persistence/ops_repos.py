"""运营侧仓储：模型目标、Outbox、术语映射、样例问题（自 operator.py 按领域聚合拆分；组合门面见 operator.py）。"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.intent.tree import ScoredIntent
from medicalrag_core.model_target import CircuitState, ModelTarget
from medicalrag_core.records import OutboxMessage

from .models import (
    ModelTargetRow,
    OutboxRow,
    QueryTermMappingRow,
    SampleQuestionRow,
)


class SqlModelTargetRepository:
    """模型目标与熔断状态持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_all(self) -> tuple[ModelTarget, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ModelTargetRow).order_by(ModelTargetRow.priority.desc())
                )
            ).all()
            return tuple(
                ModelTarget(
                    id=str(r.id),
                    name=r.name,
                    provider=r.provider,
                    model=r.model,
                    capabilities=frozenset(r.capabilities or []),
                    priority=r.priority,
                    circuit=CircuitState(r.circuit_state),
                    failures=r.failures,
                    circuit_opened_at=r.circuit_opened_at,
                )
                for r in rows
            )

    async def save(self, target: ModelTarget) -> None:
        async with self._sessions() as session:
            row = await session.get(ModelTargetRow, uuid.UUID(target.id))
            if row is None:
                session.add(
                    ModelTargetRow(
                        id=uuid.UUID(target.id),
                        name=target.name,
                        provider=target.provider,
                        model=target.model,
                        capabilities=list(target.capabilities),
                        priority=target.priority,
                        circuit_state=target.circuit.value,
                        failures=target.failures,
                        circuit_opened_at=target.circuit_opened_at,
                    )
                )
            else:
                row.name = target.name
                row.provider = target.provider
                row.model = target.model
                row.capabilities = list(target.capabilities)
                row.priority = target.priority
                row.circuit_state = target.circuit.value
                row.failures = target.failures
                row.circuit_opened_at = target.circuit_opened_at
            await session.commit()


class SqlOutboxRepository:
    """事务性 Outbox 持久化仓储（领取采用「行锁 + 租约」；具体 Relay 投递见 worker）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, message: OutboxMessage) -> None:
        async with self._sessions() as session:
            session.add(
                OutboxRow(
                    id=uuid.UUID(message.id),
                    aggregate_type=message.aggregate_type,
                    aggregate_id=message.aggregate_id,
                    event_type=message.event_type,
                    payload=dict(message.payload),
                )
            )
            await session.commit()

    async def claim(
        self,
        limit: int,
        *,
        max_attempts: int | None = None,
    ) -> tuple[OutboxMessage, ...]:
        """领取一批未处理事件并打上租约时间戳；同一事务提交后才释放行锁。

        仅靠 `FOR UPDATE SKIP LOCKED` 不够：行锁随 session 关闭（rollback）立即释放，
        多个 relay 循环会各自领到同一批消息、重复投递。因此在同一事务内写入 `claimed_at`
        再提交——提交前锁一直持有（并发 relay 会跳过），提交后由租约保证崩溃恢复：
        超过 300s 未被处理的事件自动重新可领（at-least-once，重复执行由阶段幂等约束兜底）。
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=300)
        async with self._sessions() as session:
            query = (
                select(OutboxRow)
                .where(OutboxRow.processed_at.is_(None))
                .where(
                    or_(
                        OutboxRow.claimed_at.is_(None),
                        OutboxRow.claimed_at < cutoff,
                    )
                )
                .order_by(OutboxRow.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            if max_attempts is not None:
                query = query.where(OutboxRow.attempts < max_attempts)
            rows = (await session.scalars(query)).all()
            claimed = datetime.now(UTC)
            for row in rows:
                row.claimed_at = claimed
            await session.commit()
            return tuple(
                OutboxMessage(
                    id=str(r.id),
                    aggregate_type=r.aggregate_type,
                    aggregate_id=r.aggregate_id,
                    event_type=r.event_type,
                    payload=dict(r.payload or {}),
                    created_at=str(r.created_at),
                    processed_at=str(r.processed_at) if r.processed_at else None,
                    attempts=r.attempts,
                )
                for r in rows
            )

    async def mark_processed(self, message_id: str) -> None:
        async with self._sessions() as session:
            row = await session.get(OutboxRow, uuid.UUID(message_id))
            if row is not None:
                row.processed_at = datetime.now(UTC)
                await session.commit()

    async def record_failure(self, message_id: str) -> None:
        """记录投递失败并将重试次数 +1；超过最大重试上限的消息将在 claim 阶段自动跳过（保障毒消息可追溯）。

        同时清除本租约（claimed_at=None）：否则失败消息要等满 lease_s 才能被重新领取，
        与「relay 轮询下个周期自然重试」的语义矛盾。
        """
        async with self._sessions() as session:
            row = await session.get(OutboxRow, uuid.UUID(message_id))
            if row is not None:
                row.attempts += 1
                row.claimed_at = None
                await session.commit()


class SqlQueryTermMappingRepository:
    """医学专业术语与意图节点映射持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_all(self) -> tuple[QueryTermMappingRow, ...]:
        async with self._sessions() as session:
            return tuple(
                (
                    await session.scalars(
                        select(QueryTermMappingRow).order_by(QueryTermMappingRow.created_at)
                    )
                ).all()
            )

    async def add(self, term: str, intent_node_id: str) -> None:
        async with self._sessions() as session:
            session.add(QueryTermMappingRow(term=term, intent_node_id=intent_node_id))
            await session.commit()


class SqlSampleQuestionRepository:
    """推荐样例问题配置持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_for_workspace(self, workspace_id: str) -> tuple[dict[str, object], ...]:
        """按工作区列出样例问题。"""
        async with self._sessions() as session:
            query = (
                select(SampleQuestionRow)
                .where(SampleQuestionRow.workspace_id == uuid.UUID(workspace_id))
                .order_by(SampleQuestionRow.created_at)
            )
            rows = (await session.scalars(query)).all()
            return tuple(
                {
                    "id": str(row.id),
                    "text": row.text,
                    "intent_node_id": row.intent_node_id,
                    "created_at": str(row.created_at) if row.created_at else None,
                }
                for row in rows
            )


class SqlTermIntentResolver:
    """查询词映射 → 意图候选解析器（实现 medical_core.chat.ports.TermIntentResolver 端口）。

    用户问题命中已启用映射术语时，把对应意图节点作为满分候选返回（确定性捷径，
    优先于 LLM 分类输出）。全表规模小，进程内 60s TTL 缓存避免每问一查。
    """

    _TTL_S = 60.0

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._mappings: tuple[tuple[str, str], ...] = ()
        self._loaded_at = float("-inf")

    async def _load(self) -> tuple[tuple[str, str], ...]:

        if time.monotonic() - self._loaded_at > self._TTL_S:
            async with self._sessions() as session:
                rows = (
                    await session.scalars(
                        select(QueryTermMappingRow).order_by(QueryTermMappingRow.created_at)
                    )
                ).all()
            self._mappings = tuple((row.term, row.intent_node_id) for row in rows if row.term)
            self._loaded_at = time.monotonic()
        return self._mappings

    async def resolve(self, question: str) -> tuple[ScoredIntent, ...]:
        mappings = await self._load()
        lowered = question.lower()
        out: list[ScoredIntent] = []
        seen: set[str] = set()
        for term, node_id in mappings:
            if node_id in seen:
                continue
            if term.lower() in lowered:
                seen.add(node_id)
                out.append(ScoredIntent(node_id=node_id, score=1.0))
        return tuple(out)
