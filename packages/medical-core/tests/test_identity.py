"""身份域检查：会话生命周期（ADR 0019）与注册/认证（ADR 0018）。"""

import pytest

from medicalrag_core.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidCredentialsError,
)
from medicalrag_core.identity.sessions import SessionManager
from medicalrag_core.identity.user import User


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password: str, encoded: str) -> bool:
        return encoded == f"hash:{password}"


class FakeSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, float]] = {}
        self._now = 0.0

    def tick(self, seconds: float) -> None:
        self._now += seconds

    async def save(self, token: str, user_id: str, *, ttl_s: int) -> None:
        self._sessions[token] = (user_id, self._now + ttl_s)

    async def load(self, token: str) -> str | None:
        entry = self._sessions.get(token)
        if entry is None:
            return None
        user_id, expiry = entry
        return user_id if self._now < expiry else None

    async def delete(self, token: str) -> None:
        self._sessions.pop(token, None)


class FakeUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def create(self, user: User) -> None:
        self._users[user.email] = user

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)

    async def get_by_id(self, user_id: str) -> User | None:
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None


async def test_session_create_returns_csp_rng_token():
    store = FakeSessionStore()
    token = await SessionManager(store).create("user-1")
    assert len(token) >= 32
    assert token.isalnum() or "-" in token or "_" in token  # url-safe


async def test_session_validate_and_revoke():
    store = FakeSessionStore()
    manager = SessionManager(store)
    token = await manager.create("user-1")
    assert await manager.validate(token) == "user-1"
    await manager.revoke(token)
    assert await manager.validate(token) is None


async def test_session_expired_returns_none():
    store = FakeSessionStore()
    manager = SessionManager(store, ttl_s=60)
    token = await manager.create("user-1")
    store.tick(61)
    assert await manager.validate(token) is None


async def test_register_hashes_password_and_returns_user_id():
    users = FakeUserRepository()
    service = IdentityService(users, FakePasswordHasher())
    user_id = await service.register("a@example.com", "secret")
    assert user_id
    user = await users.get_by_email("a@example.com")
    assert user is not None
    assert user.password_hash == "hash:secret"
    assert user.password_hash != "secret"


async def test_register_duplicate_email_raises():
    service = IdentityService(FakeUserRepository(), FakePasswordHasher())
    await service.register("a@example.com", "secret")
    with pytest.raises(DuplicateUserError):
        await service.register("a@example.com", "other")


async def test_authenticate_success_returns_user_id():
    service = IdentityService(FakeUserRepository(), FakePasswordHasher())
    user_id = await service.register("a@example.com", "secret")
    assert await service.authenticate("a@example.com", "secret") == user_id


async def test_authenticate_wrong_password_raises():
    service = IdentityService(FakeUserRepository(), FakePasswordHasher())
    await service.register("a@example.com", "secret")
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("a@example.com", "wrong")


async def test_authenticate_unknown_email_raises():
    service = IdentityService(FakeUserRepository(), FakePasswordHasher())
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("ghost@example.com", "x")
