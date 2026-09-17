"""用户注册与身份认证服务（应用自有的身份管理领域服务）。"""

from __future__ import annotations

from ..ids import uuid7
from .ports import PasswordHasher, UserRepository
from .user import User


class DuplicateUserError(ValueError):
    """当尝试注册已存在的邮箱地址时抛出该异常。"""


class InvalidCredentialsError(ValueError):
    """邮箱或密码不匹配异常（统一报错信息，防止用户枚举攻击）。"""


class IdentityService:
    """用户注册与身份认证服务；校验成功后返回 user_id，会话签发交由调用方（API 组合根）处理。"""

    def __init__(self, users: UserRepository, passwords: PasswordHasher) -> None:
        self._users = users
        self._passwords = passwords
        # 用端口自身生成哑哈希（不耦合具体算法格式）；对未知邮箱也执行一次真实代价的
        # 哈希校验，抹平响应时序差，与统一报错文案共同实现防用户枚举
        self._dummy_hash = passwords.hash("medicalrag:timing-equalizer")

    async def register(self, email: str, password: str) -> str:
        """创建新用户并执行密码哈希加密；邮箱已存在时抛出 DuplicateUserError。"""
        if await self._users.get_by_email(email) is not None:
            raise DuplicateUserError(email)
        user = User(
            id=str(uuid7()),
            email=email,
            password_hash=self._passwords.hash(password),
        )
        await self._users.create(user)
        return user.id

    async def authenticate(self, email: str, password: str) -> str:
        """校验用户凭据并返回 user_id；凭据无效时抛出 InvalidCredentialsError。"""
        user = await self._users.get_by_email(email)
        if user is None:
            self._passwords.verify(password, self._dummy_hash)
            raise InvalidCredentialsError(email)
        if not self._passwords.verify(password, user.password_hash):
            raise InvalidCredentialsError(email)
        return user.id
