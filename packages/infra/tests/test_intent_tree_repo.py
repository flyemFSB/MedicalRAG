"""SqlIntentTreeRepository SQLite 行为检查。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.intent_tree import SqlIntentTreeRepository
from medicalrag_infra.persistence.models import Base, IntentNodeRow


@pytest.fixture
async def factory() -> async_sessionmaker[AsyncSession]:
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


async def _seed(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        session.add_all(
            [
                IntentNodeRow(id="medical", level="domain", kind="knowledge", name="医学"),
                IntentNodeRow(
                    id="disease-info",
                    level="topic",
                    kind="knowledge",
                    name="疾病信息",
                    parent_id="medical",
                    description="疾病基本信息",
                    examples=["什么是高血压"],
                    enabled=True,
                ),
                IntentNodeRow(
                    id="disabled-node",
                    level="topic",
                    kind="knowledge",
                    name="已禁用",
                    parent_id="medical",
                    enabled=False,
                ),
            ]
        )
        await session.commit()


async def test_load_builds_tree_with_eligible_leaves(factory):
    await _seed(factory)
    tree = await SqlIntentTreeRepository(factory).load()
    leaves = {n.id: n for n in tree.eligible_leaves()}
    assert "disease-info" in leaves
    assert "disabled-node" not in leaves
    node = leaves["disease-info"]
    assert node.examples == ("什么是高血压",)
    assert node.parent_id == "medical"
