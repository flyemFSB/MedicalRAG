"""SqlIngestionRunRepository SQLite 行为检查（阶段幂等 + 只前向，ADR 0013/0063）。"""

import uuid

import pytest

from medicalrag_core.ingestion.state_machine import IngestionRunState, InvalidIngestionTransition
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.ingestion import SqlIngestionRunRepository
from medicalrag_infra.persistence.models import Base


@pytest.fixture
async def repo() -> SqlIngestionRunRepository:
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SqlIngestionRunRepository(factory)
    await engine.dispose()


async def test_create_run_returns_uuid7_accepted(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid.uuid7()), str(uuid.uuid7()))
    assert uuid.UUID(run_id).version == 7
    assert await repo.state(run_id) is IngestionRunState.ACCEPTED


async def test_complete_stage_progresses_through_all_stages(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid.uuid7()), str(uuid.uuid7()))
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
    run_id = await repo.create_run(str(uuid.uuid7()), str(uuid.uuid7()))
    assert (
        await repo.complete_stage(run_id, IngestionRunState.ACCEPTED)
        is IngestionRunState.EXTRACTING
    )
    assert (
        await repo.complete_stage(run_id, IngestionRunState.ACCEPTED)
        is IngestionRunState.EXTRACTING
    )


async def test_terminal_state_cannot_advance(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid.uuid7()), str(uuid.uuid7()))
    state = IngestionRunState.ACCEPTED
    for _ in range(8):
        state = await repo.complete_stage(run_id, state)
    with pytest.raises(InvalidIngestionTransition):
        await repo.complete_stage(run_id, IngestionRunState.PUBLISHED)


async def test_stale_stage_raises(repo: SqlIngestionRunRepository):
    run_id = await repo.create_run(str(uuid.uuid7()), str(uuid.uuid7()))
    with pytest.raises(InvalidIngestionTransition):
        await repo.complete_stage(run_id, IngestionRunState.EXTRACTING)  # 当前为 ACCEPTED
