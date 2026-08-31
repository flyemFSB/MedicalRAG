"""SqlUserRepository SQLite 行为检查。"""

import uuid

import pytest

from medicalrag_core.identity.user import User
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base
from medicalrag_infra.persistence.users import SqlUserRepository


@pytest.fixture
async def repo() -> SqlUserRepository:
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SqlUserRepository(factory)
    await engine.dispose()


async def test_create_and_get_by_email(repo: SqlUserRepository):
    user = User(id=str(uuid.uuid7()), email="a@example.com", password_hash="hash")
    await repo.create(user)
    found = await repo.get_by_email("a@example.com")
    assert found is not None
    assert found.id == user.id
    assert found.email == "a@example.com"
    assert found.password_hash == "hash"


async def test_get_by_email_unknown_returns_none(repo: SqlUserRepository):
    assert await repo.get_by_email("ghost@example.com") is None
