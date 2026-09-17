"""SqlIngestionRunRepository SQLite 行为检查（阶段幂等 + 只前向，ADR 0013/0063）。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.state_machine import IngestionRunState, InvalidIngestionTransition
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.ingestion import SqlIngestionRunRepository
from medicalrag_infra.persistence.models import Base


@pytest.fixture
async def factory(persistence_url: str) -> async_sessionmaker[AsyncSession]:
    engine, session_factory = create_engine_and_session_factory(persistence_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def repo(factory: async_sessionmaker[AsyncSession]) -> SqlIngestionRunRepository:
    return SqlIngestionRunRepository(factory)


async def test_create_run_returns_uuid7_accepted(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    assert uuid.UUID(run_id).version == 7
    assert await repo.state(run_id) is IngestionRunState.ACCEPTED


async def test_complete_stage_progresses_through_all_stages(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    state = IngestionRunState.ACCEPTED
    for target in [
        IngestionRunState.EXTRACTING,
        IngestionRunState.EXTRACTED,
        IngestionRunState.CHUNKING,
        IngestionRunState.ENRICHING,
        IngestionRunState.EMBEDDING,
        IngestionRunState.INDEXING,
        IngestionRunState.VALIDATING,
        IngestionRunState.PUBLISHED,
    ]:
        state = await repo.complete_stage(run_id, state)
        assert state is target
    assert await repo.state(run_id) is IngestionRunState.PUBLISHED


async def test_retry_of_completed_stage_is_noop(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    assert (
        await repo.complete_stage(run_id, IngestionRunState.ACCEPTED)
        is IngestionRunState.EXTRACTING
    )
    assert (
        await repo.complete_stage(run_id, IngestionRunState.ACCEPTED)
        is IngestionRunState.EXTRACTING
    )


async def test_terminal_state_cannot_advance(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    state = IngestionRunState.ACCEPTED
    for _ in range(8):
        state = await repo.complete_stage(run_id, state)
    with pytest.raises(InvalidIngestionTransition):
        await repo.complete_stage(run_id, IngestionRunState.PUBLISHED)


async def test_stale_stage_raises(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    with pytest.raises(InvalidIngestionTransition):
        await repo.complete_stage(run_id, IngestionRunState.EXTRACTING)  # 当前为 ACCEPTED


async def test_mark_failed_records_stage_and_resume_restores(repo: SqlIngestionRunRepository):
    """FAILED 重放契约：mark_failed 记录失败阶段；resume_failed 仅在阶段匹配时复位（CAS 语义）。"""
    run_id = await repo.create_run(str(uuid7()), str(uuid7()))
    await repo.complete_stage(run_id, IngestionRunState.ACCEPTED)  # -> EXTRACTING
    # 失败阶段不存在时的重放请求被拒绝
    assert await repo.resume_failed(run_id, IngestionRunState.CHUNKING) is False
    await repo.mark_failed(run_id, "MinerUError")
    meta = await repo.metadata(run_id)
    assert meta["failed_stage"] == "extracting"
    assert meta["failure_reason"] == "MinerUError"
    assert await repo.state(run_id) is IngestionRunState.FAILED
    # 阶段不匹配 → 不复位；匹配 → 复位后可继续推进
    assert await repo.resume_failed(run_id, IngestionRunState.CHUNKING) is False
    assert await repo.resume_failed(run_id, IngestionRunState.EXTRACTING) is True
    assert await repo.state(run_id) is IngestionRunState.EXTRACTING
    assert (
        await repo.complete_stage(run_id, IngestionRunState.EXTRACTING)
        is IngestionRunState.EXTRACTED
    )


async def test_fail_stale_runs_only_touches_stale_non_terminal(
    repo: SqlIngestionRunRepository, factory: async_sessionmaker[AsyncSession]
):
    """僵尸 Run 自愈：updated_at 停滞的超龄非终态 Run 置为 FAILED，终态与新 Run 不受影响。"""
    stale = await repo.create_run(str(uuid7()), str(uuid7()))
    fresh = await repo.create_run(str(uuid7()), str(uuid7()))
    done = await repo.create_run(str(uuid7()), str(uuid7()))
    await repo.complete_stage(done, IngestionRunState.ACCEPTED)
    # 把 stale 的 updated_at 拨回 1 小时前
    from datetime import timedelta

    from medicalrag_infra.persistence.models import IngestionRun

    async with factory() as session:
        row = await session.get(IngestionRun, uuid.UUID(stale))
        row.updated_at = row.updated_at - timedelta(hours=1)
        await session.commit()
    count = await repo.fail_stale_runs(max_age_s=600)
    assert count == 1
    assert await repo.state(stale) is IngestionRunState.FAILED
    assert await repo.state(fresh) is IngestionRunState.ACCEPTED
    assert (
        await repo.state(done) is IngestionRunState.EXTRACTING
    )  # 已推进的非终态且未超龄，不受影响
