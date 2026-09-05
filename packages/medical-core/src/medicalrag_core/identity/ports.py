"""身份认证与用户域的适配器端口协议（应用自有的身份基础设施契约）。"""

from __future__ import annotations

from typing import Protocol

from .user import User


class PasswordHasher(Protocol):
    """密码安全哈希端口；校验失败返回 False（错误时模糊处理，防止泄露内部失败阶段）。"""

    def hash(self, password: str) -> str: ...
    def verify(self, password: str, encoded: str) -> bool: ...


class SessionStore(Protocol):
    """服务端会话存储端口：管理 token → user_id 的映射，支持 TTL 自动过期。"""

    async def save(self, token: str, user_id: str, *, ttl_s: int) -> None: ...
    async def load(self, token: str) -> str | None: ...
    async def delete(self, token: str) -> None: ...


class UserRepository(Protocol):
    """用户存储仓储端口：支持基于邮箱或用户 ID 的查询以及新用户创建（邮箱全局唯一）。"""

    async def create(self, user: User) -> None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
