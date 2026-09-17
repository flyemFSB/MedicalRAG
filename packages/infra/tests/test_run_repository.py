"""Run 仓库 SQLite 行为检查（spec：SQLite 跑仓库行为，PostgreSQL 走集成 profile）。"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.model import ChatRequest, ChatResult, Outcome
from medicalrag_core.chat.run_state import ChatRunState
from medicalrag_core.ids import uuid7
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base, ChatRun, RunEvent
from medicalrag_infra.persistence.run_repository import SqlRunRepository


@pytest.fixture
async def repo(
    persistence_url: str,
) -> tuple[SqlRunRepository, async_sessionmaker[AsyncSession]]:
    engine, factory = create_engine_and_session_factory(persistence_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SqlRunRepository(factory), factory
    await engine.dispose()


def _request(**overrides) -> ChatRequest:
    defaults = {
        "question": "高血压应该注意什么？",
        "conversation_id": str(uuid7()),
        "user_id": str(uuid7()),
        "workspace_id": str(uuid7()),
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


async def test_create_run_returns_uuid7_and_accepted(
    repo: tuple[SqlRunRepository, async_sessionmaker[AsyncSession]],
):
    adapter, factory = repo
    run_id = await adapter.create_run(_request())
    parsed = uuid.UUID(run_id)
    assert parsed.version == 7
    async with factory() as session:
        run = await session.get(ChatRun, parsed)
        assert run is not None
        assert run.status == ChatRunState.ACCEPTED.value


async def test_record_state_updates_status_and_records_event(
    repo: tuple[SqlRunRepository, async_sessionmaker[AsyncSession]],
):
    adapter, factory = repo
    run_id = await adapter.create_run(_request())
    await adapter.record_state(run_id, ChatRunState.GENERATING)
    async with factory() as session:
        run = await session.get(ChatRun, uuid.UUID(run_id))
        assert run.status == ChatRunState.GENERATING.value
        events = (
            (await session.execute(select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id))))
            .scalars()
            .all()
        )
        assert [e.event for e in events] == [ChatRunState.GENERATING.value]


async def test_complete_sets_terminal_fields(
    repo: tuple[SqlRunRepository, async_sessionmaker[AsyncSession]],
):
    adapter, factory = repo
    run_id = await adapter.create_run(_request())
    result = ChatResult(
        outcome=Outcome.ANSWERED,
        message="回答",
        run_id=run_id,
        retrieval_policy_version=3,
        trace_id="trace-1",
    )
    await adapter.complete(run_id, result)
    async with factory() as session:
        run = await session.get(ChatRun, uuid.UUID(run_id))
        assert run.status == ChatRunState.COMPLETED.value
        assert run.outcome == Outcome.ANSWERED.value
        assert run.assistant_message == "回答"
        assert run.retrieval_policy_version == 3
        assert run.trace_id == "trace-1"
        assert run.completed_at is not None


async def test_record_state_unknown_run_raises(
    repo: tuple[SqlRunRepository, async_sessionmaker[AsyncSession]],
):
    adapter, _ = repo
    with pytest.raises(KeyError):
        await adapter.record_state(str(uuid7()), ChatRunState.ANALYZED)
