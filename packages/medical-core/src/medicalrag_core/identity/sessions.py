"""服务端会话生命周期管理（ADR 0019）。

会话令牌采用高安全随机数生成（secrets.token_urlsafe(32)，熵值 ≥128 位），
由服务端持久化 token → user_id 的映射关系；登录成功后必须强制重新生成令牌，以防范会话固定（Session Fixation）安全漏洞。
"""

from __future__ import annotations

import secrets

from .ports import SessionStore


class SessionManager:
    """服务端会话管理器：负责创建、校验与吊销会话令牌；令牌本身不携带业务载荷，仅作为底层存储的索引键。"""

    def __init__(self, store: SessionStore, *, ttl_s: int = 86400) -> None:
        self._store = store
        self._ttl = ttl_s

    async def create(self, user_id: str) -> str:
        """生成新的安全会话令牌并持久化入库；返回令牌字符串用于下发 Cookie。"""
        token = secrets.token_urlsafe(32)
        await self._store.save(token, user_id, ttl_s=self._ttl)
        return token

    async def validate(self, token: str) -> str | None:
        """校验会话令牌的有效性；若校验通过返回对应的 user_id，若令牌无效或已过期则返回 None。"""
        return await self._store.load(token)

    async def revoke(self, token: str) -> None:
        """吊销指定的会话令牌，使其立即失效。"""
        await self._store.delete(token)
