"""会话记忆（SqlMemory）SQLite 行为检查。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.chat.model import ChatRequest, Message, MessageRole
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.memory import SqlMemory
from medicalrag_infra.persistence.models import Base


@pytest.fixture
async def factory() -> async_sessionmaker[AsyncSession]:
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


def _request(**overrides) -> ChatRequest:
    defaults = {
        "question": "q",
        "conversation_id": str(uuid.uuid7()),
        "user_id": str(uuid.uuid7()),
        "workspace_id": str(uuid.uuid7()),
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


async def test_append_then_load_returns_messages_in_order(
    factory: async_sessionmaker[AsyncSession],
):
    adapter = SqlMemory(factory)
    request = _request()
    for i in range(3):
        await adapter.append(request, Message(role=MessageRole.USER, text=f"u{i}"))
        await adapter.append(request, Message(role=MessageRole.ASSISTANT, text=f"a{i}"))
    context = await adapter.load(request)
    assert [m.text for m in context.messages] == ["u0", "a0", "u1", "a1", "u2", "a2"]


async def test_load_returns_only_recent_window(
    factory: async_sessionmaker[AsyncSession],
):
    adapter = SqlMemory(factory, window=3)
    request = _request()
    for i in range(5):
        await adapter.append(request, Message(role=MessageRole.USER, text=f"u{i}"))
    context = await adapter.load(request)
    assert [m.text for m in context.messages] == ["u2", "u3", "u4"]


async def test_load_is_scoped_to_conversation_and_workspace(
    factory: async_sessionmaker[AsyncSession],
):
    adapter = SqlMemory(factory)
    request = _request()
    other = _request(conversation_id=str(uuid.uuid7()), workspace_id=request.workspace_id)
    await adapter.append(request, Message(role=MessageRole.USER, text="mine"))
    await adapter.append(other, Message(role=MessageRole.USER, text="theirs"))
    context = await adapter.load(request)
    assert [m.text for m in context.messages] == ["mine"]


async def test_load_empty_conversation(factory: async_sessionmaker[AsyncSession]):
    adapter = SqlMemory(factory)
    context = await adapter.load(_request())
    assert context.messages == ()
