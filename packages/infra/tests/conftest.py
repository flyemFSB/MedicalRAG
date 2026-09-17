"""持久化层测试的数据库接缝（本目录所有仓储测试共用）。

默认 SQLite 内存库：零依赖、快。配了 ``MEDICALRAG_TEST_DATABASE_URL`` 则改用真 PostgreSQL——
timestamptz 时区语义、uuid 原生类型、约束与默认值这些差异只有真库能暴露，仓储行为必须两种方言都成立。

真库模式下每个测试前后都清空 schema：``outbox.claim`` 这类断言的是绝对行数，
共享库残留行会把断言变成跨测试耦合（假绿或随机红）。
``alembic_version`` 一并清除——迁移门禁（apps/api）与仓储测试共用同一个测试库，
残留的版本行会让 ``alembic upgrade`` 空跑、``command.check`` 假绿。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base


async def _drop_schema(url: str) -> None:
    engine, _ = create_engine_and_session_factory(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


@pytest.fixture
async def persistence_url() -> AsyncIterator[str]:
    """测试库 URL：配置了真 PostgreSQL 用真库，并在使用前后清理 schema；否则退化为内存 SQLite。"""
    url = os.environ.get("MEDICALRAG_TEST_DATABASE_URL", "sqlite+aiosqlite://")
    if url.startswith("sqlite"):
        yield url
        return
    await _drop_schema(url)
    try:
        yield url
    finally:
        await _drop_schema(url)
