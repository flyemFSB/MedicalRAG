"""身份域检查：用户注册/认证（ADR 0018）。会话签发在 API 组合根（secrets + SessionStore）。"""

import pytest

from medicalrag_core.identity.service import (
    DuplicateUserError,
    IdentityService,
    InvalidCredentialsError,
)
from medicalrag_core.identity.user import User


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password: str, encoded: str) -> bool:
        return encoded == f"hash:{password}"


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
