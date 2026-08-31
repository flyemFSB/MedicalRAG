"""CachedEmbeddingProvider 检查（fake Redis，确定性）。"""

import json

from medicalrag_infra.providers.embeddings import CachedEmbeddingProvider


class FakeRedis:
    """mget/set/pipeline 最小实现（进程内 dict）。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.inner_calls = 0

    async def mget(self, keys):
        return [self.store.get(k) for k in keys]

    def pipeline(self):
        return self

    def set(self, key, value, ex=None):
        self._pending = getattr(self, "_pending", {})
        self._pending[key] = value
        return self

    async def execute(self):
        self.store.update(getattr(self, "_pending", {}))
        self._pending = {}


class FakeInner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[0.1, 0.2] for _ in texts]


async def test_cache_hits_skip_inner_and_backfill_misses():
    redis = FakeRedis()
    inner = FakeInner()
    provider = CachedEmbeddingProvider(inner, redis)

    first = await provider.embed(["高血压定义", "降压目标"])
    assert len(first) == 2
    assert inner.calls == [["高血压定义", "降压目标"]]

    # 全命中：不再调 inner
    second = await provider.embed(["高血压定义", "降压目标"])
    assert second == first
    assert inner.calls == [["高血压定义", "降压目标"]]
    assert len(redis.store) == 2

    # 部分未命中：只回填缺失文本
    await provider.embed(["高血压定义", "新查询"])
    assert inner.calls[-1] == ["新查询"]
    assert json.loads(redis.store[provider._key("新查询")]) == [0.1, 0.2]


async def test_redis_failure_fails_open_to_inner():
    class BrokenRedis:
        async def mget(self, keys):
            raise ConnectionError("redis down")

    inner = FakeInner()
    provider = CachedEmbeddingProvider(inner, BrokenRedis())
    result = await provider.embed(["q1", "q2"])
    assert len(result) == 2
    assert inner.calls == [["q1", "q2"]]
