"""请求限流适配器：基于 Redis 的固定窗口限流与本地内存降级实现（规范用户故事 28）。

生产环境采用 Redis `INCR` + `EXPIRE` 管道原子操作（单次 RTT 网络往返），当超过配额时返回 False；
在 Redis 未配置或故障时自动降级为进程内内存计数器（适用于本地开发单进程场景，配合健康检查返回 degraded 状态）。
"""

from __future__ import annotations

import asyncio
import time

from redis.asyncio import Redis


class RedisRateLimiter:
    """基于 Redis 的固定窗口原子限流器。"""

    def __init__(self, client: Redis) -> None:
        self._client = client
        self._prefix = "rl"

    async def acquire(self, key: str, *, limit: int, window_s: float) -> bool:
        """固定窗口计数：仅首个请求设置 TTL（NX）。

        每次请求都无条件 `EXPIRE` 会不断刷新 TTL，持续流量下计数器永不过期，
        最终把正常用户永久锁在 429（Redis 官方 INCR 限流模式的 Pattern 2 语义）。
        用 pexpire 支持亚秒窗口（int(window_s) 会把 <1s 截断为 0 = 立即删 key）。
        """
        redis_key = f"{self._prefix}:{key}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.pexpire(redis_key, max(1, int(window_s * 1000)), nx=True)
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


class RedisConcurrencyGate:
    """Redis 分布式并发闸：限制同时占用的会话槽位数，获取不到时在预算内等待（排队）。

    简化版公平排队：以等待先到先抢代替严格 FIFO 队首仲裁（当前并发量级下足够）。
    租约语义：每个槽位成员的 score 为持有者的到期时间戳（成员级租约），
    claim 时先清理全部过期成员再计数——持有者进程崩溃后其槽位随租约到期自动回收。
    """

    # 槽位租约时长：持有者须在租约内完成请求并释放；崩溃者的槽位过期后由后续 claim 回收
    _LEASE_MS = 600_000
    # 整个 ZSET key 的兜底 TTL（≥ 租约时长）：彻底空闲的 key 过期自清，避免长期占用键空间
    _KEY_TTL_MS = 1_200_000
    _CLAIM = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[3])
    local n = redis.call('ZCARD', KEYS[1])
    if n < tonumber(ARGV[1]) then
        redis.call('ZADD', KEYS[1], ARGV[3], ARGV[2])
        redis.call('PEXPIRE', KEYS[1], ARGV[4])
        return 1
    end
    return 0
    """

    def __init__(self, client: Redis, *, prefix: str = "chatgate") -> None:
        self._client = client
        self._prefix = prefix

    async def acquire(self, name: str, *, limit: int, holder: str, wait_s: float) -> bool:
        """尝试占用一个并发槽位；未满立即成功，已满则每 0.25s 重试直至超时。"""
        key = f"{self._prefix}:{name}"
        deadline = time.monotonic() + wait_s
        while True:
            expires_at = int(time.time() * 1000) + self._LEASE_MS
            granted = await self._client.eval(
                self._CLAIM,
                1,
                key,
                limit,
                holder,
                expires_at,
                self._KEY_TTL_MS,
            )
            if int(granted) == 1:
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.25)

    async def release(self, name: str, holder: str) -> None:
        """释放并发槽位（持有者不匹配时为空操作；崩溃场景由成员级租约过期回收）。"""
        await self._client.zrem(f"{self._prefix}:{name}", holder)
