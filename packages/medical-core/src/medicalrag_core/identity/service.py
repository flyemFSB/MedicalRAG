"""用户注册与身份认证服务（应用自有的身份管理领域服务，ADR 0018）。"""

from __future__ import annotations

import uuid

from .ports import PasswordHasher, UserRepository
from .user import User


class DuplicateUserError(ValueError):
    """当尝试注册已存在的邮箱地址时抛出该异常。"""


class InvalidCredentialsError(ValueError):
    """邮箱或密码不匹配异常（统一报错信息，防止用户枚举攻击）。"""


class IdentityService:
    """用户注册与身份认证服务；校验成功后返回 user_id，会话创建交由调用方（API 层）通过 SessionManager 处理。"""

    def __init__(self, users: UserRepository, passwords: PasswordHasher) -> None:
        self._users = users
        self._passwords = passwords

    async def register(self, email: str, password: str) -> str:
        """创建新用户并执行密码哈希加密；邮箱已存在时抛出 DuplicateUserError。"""
        if await self._users.get_by_email(email) is not None:
            raise DuplicateUserError(email)
        user = User(
            id=str(uuid.uuid7()),
            email=email,
            password_hash=self._passwords.hash(password),
        )
        await self._users.create(user)
        return user.id

    async def authenticate(self, email: str, password: str) -> str:
        """校验用户凭据并返回 user_id；凭据无效时抛出 InvalidCredentialsError。"""
        user = await self._users.get_by_email(email)
        if user is None or not self._passwords.verify(password, user.password_hash):
            raise InvalidCredentialsError(email)
        return user.id

    async def get_user(self, user_id: str) -> User | None:
        """根据 ID 获取用户信息（供 /me 等需要用户实体的端点使用）。"""
        return await self._users.get_by_id(user_id)
