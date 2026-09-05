"""服务端会话存储适配器：基于 Redis 的分布式会话存储与进程内内存降级实现（服务端会话 + 安全 Cookie）。

生产环境依托 Redis TTL 机制自动清理过期会话；在本地开发或未配置 Redis 时，显式降级为基于单调时钟的进程内存储，
同时就绪探针（readiness probe）将健康状态标记为 degraded，不静默掩盖依赖缺失。
"""

from __future__ import annotations

import time

from redis.asyncio import Redis


class RedisSessionStore:
    """实现 SessionStore 协议端口；会话 TTL 依托 Redis Key 的原生过期机制保障。"""

    def __init__(self, client: Redis, *, prefix: str = "session:") -> None:
        self._client = client
        self._prefix = prefix

    def _key(self, token: str) -> str:
        return f"{self._prefix}{token}"

    async def save(self, token: str, user_id: str, *, ttl_s: int) -> None:
        await self._client.set(self._key(token), user_id, ex=ttl_s)

    async def load(self, token: str) -> str | None:
        value = await self._client.get(self._key(token))
        return value.decode() if isinstance(value, bytes) else value

    async def delete(self, token: str) -> None:
        await self._client.delete(self._key(token))


class InMemorySessionStore:
    """进程内内存会话存储（供本地单进程开发与测试使用）；TTL 基于单调时钟实现。"""

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, float]] = {}

    async def save(self, token: str, user_id: str, *, ttl_s: int) -> None:
        self._sessions[token] = (user_id, time.monotonic() + ttl_s)

    async def load(self, token: str) -> str | None:
        entry = self._sessions.get(token)
        if entry is None:
            return None
        user_id, expiry = entry
        return user_id if time.monotonic() < expiry else None

    async def delete(self, token: str) -> None:
        self._sessions.pop(token, None)
