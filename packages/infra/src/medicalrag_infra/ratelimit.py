"""请求限流适配器：基于 Redis 的滑动窗口限流与本地内存降级实现（规范用户故事 28）。

生产环境采用 Redis `INCR` + `EXPIRE` 管道原子操作（单次 RTT 网络往返），当超过配额时返回 False；
在 Redis 未配置或故障时自动降级为进程内内存计数器（适用于本地开发单进程场景，配合健康检查返回 degraded 状态）。
"""

from __future__ import annotations

import time

from redis.asyncio import Redis


class RedisRateLimiter:
    """基于 Redis 的固定窗口原子限流器。"""

    def __init__(self, client: Redis, *, prefix: str = "rl") -> None:
        self._client = client
        self._prefix = prefix

    async def acquire(self, key: str, *, limit: int, window_s: float) -> bool:
        redis_key = f"{self._prefix}:{key}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, int(window_s))
            current = await pipe.execute()
        count = current[0]
        return int(count) <= limit


class InMemoryRateLimiter:
    """进程内内存限流器（供本地开发与单元测试使用，不跨进程共享）。"""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, int, float], tuple[int, float]] = {}

    async def acquire(self, key: str, *, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        bucket = (key, limit, window_s)
        count, start = self._buckets.get(bucket, (0, now))
        if now - start >= window_s:
            count, start = 0, now
        if count >= limit:
            self._buckets[bucket] = (count, start)
            return False
        self._buckets[bucket] = (count + 1, start)
        return True
