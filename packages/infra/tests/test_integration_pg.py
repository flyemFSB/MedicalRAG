"""PostgreSQL 真集成测试（ADR 0080 测试金字塔中层）。

前置：`docker compose --profile test up -d postgres-test`，然后
`MEDICALRAG_TEST_DATABASE_URL=postgresql+asyncpg://medicalrag_test:medicalrag_test@127.0.0.1:5433/medicalrag_test uv run pytest -m integration`
未配置环境变量时整文件跳过（单元层不依赖外部服务）。
"""

import os
import uuid

import pytest

from medicalrag_core.identity.user import User
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base
from medicalrag_infra.persistence.users import SqlUserRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("MEDICALRAG_TEST_DATABASE_URL"),
        reason="需要 MEDICALRAG_TEST_DATABASE_URL（compose --profile test）",
    ),
]


@pytest.fixture
async def repo() -> SqlUserRepository:
    engine, factory = create_engine_and_session_factory(os.environ["MEDICALRAG_TEST_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SqlUserRepository(factory)
    await engine.dispose()


async def test_user_roundtrip_on_real_postgres(repo: SqlUserRepository):
    email = f"it-{uuid.uuid7()}@example.com"
    user = User(id=str(uuid.uuid7()), email=email, password_hash="hash")
    await repo.create(user)
    found = await repo.get_by_email(email)
    assert found is not None
    assert found.id == user.id
