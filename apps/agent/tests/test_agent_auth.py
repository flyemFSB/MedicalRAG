"""Aegra authenticate 安全语义（Cookie 解析 → 会话 → 工作区隔离）。

接缝：`medicalrag_agent.entry.authenticate`。不测真实 Redis/PG——
会话与 membership 用进程内 fake，只钉「无会话/过期/成功/降级」可观察决策。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

import medicalrag_agent.entry as entry
from medicalrag_infra.auth.sessions import InMemorySessionStore, session_cookie_name


class FakeRedis:
    """仅实现 RedisSessionStore 用到的 get/set（够 load/save 路径）。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self._data[key] = value


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    redis = FakeRedis()
    monkeypatch.setattr(entry, "_get_redis", lambda: redis)
    return redis


@pytest.fixture
def workspace_ok(monkeypatch):
    async def _ids(user_id: str) -> list[str]:
        return [f"ws-{user_id}"]

    monkeypatch.setattr(entry, "_workspace_ids", _ids)


async def test_no_cookie_returns_empty_dict(fake_redis):
    assert await entry.authenticate({}) == {}
    assert await entry.authenticate({"Cookie": ""}) == {}


async def test_unknown_session_returns_empty_dict(fake_redis):
    headers = {"Cookie": f"{session_cookie_name(True)}=no-such-token"}
    assert await entry.authenticate(headers) == {}


async def test_valid_session_injects_identity_and_workspaces(fake_redis, workspace_ok):
    # RedisSessionStore 的 key 是 session:<token>
    await fake_redis.set("session:tok-ok", "user-42")
    headers = {"Cookie": f"{session_cookie_name(True)}=tok-ok"}
    assert await entry.authenticate(headers) == {
        "identity": "user-42",
        "workspace_ids": ["ws-user-42"],
    }


async def test_plain_cookie_name_also_accepted(fake_redis, workspace_ok):
    # 本地 HTTP 用普通名；生产用 __Host-。两者都必须可解析，否则环境切换会全站 401。
    await fake_redis.set("session:tok-plain", "user-7")
    headers = {"Cookie": f"{session_cookie_name(False)}=tok-plain"}
    assert await entry.authenticate(headers) == {
        "identity": "user-7",
        "workspace_ids": ["ws-user-7"],
    }


async def test_expired_inmemory_session_is_rejected(monkeypatch):
    store = InMemorySessionStore()
    await store.save("tok-dead", "user-1", ttl_s=0)  # TTL 已到期
    monkeypatch.setattr(entry, "_get_redis", lambda: object())
    monkeypatch.setattr("medicalrag_infra.auth.sessions.RedisSessionStore", lambda _redis: store)
    headers = {"Cookie": f"{session_cookie_name(True)}=tok-dead"}
    assert await entry.authenticate(headers) == {}


async def test_workspace_lookup_failure_degrades_to_empty(fake_redis, monkeypatch):
    """DB 故障时只丢隔离上下文，不得放行带身份的空工作区跨库检索。"""

    class BoomMembership:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def memberships_of(self, _user_id: str):
            raise SQLAlchemyError("db down")

    await fake_redis.set("session:tok-ok", "user-9")
    monkeypatch.setattr(entry, "SqlMembershipRepository", BoomMembership)
    monkeypatch.setattr(entry, "_get_session_factory", lambda: object())
    headers = {"Cookie": f"{session_cookie_name(True)}=tok-ok"}
    result = await entry.authenticate(headers)
    assert result == {"identity": "user-9", "workspace_ids": []}
