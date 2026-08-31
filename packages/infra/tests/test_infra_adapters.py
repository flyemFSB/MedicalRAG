"""限流 / 本地对象存储 / 指标 适配器检查。"""

import pytest

from medicalrag_core.storage.ports import ObjectRef
from medicalrag_infra.metrics import Metrics
from medicalrag_infra.ratelimit import InMemoryRateLimiter
from medicalrag_infra.storage.local import LocalObjectStorage


async def test_in_memory_rate_limiter_allows_until_limit():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        assert await limiter.acquire("user-1", limit=3, window_s=60)
    assert not await limiter.acquire("user-1", limit=3, window_s=60)


async def test_in_memory_rate_limiter_is_per_key():
    limiter = InMemoryRateLimiter()
    assert await limiter.acquire("a", limit=1, window_s=60)
    assert not await limiter.acquire("a", limit=1, window_s=60)
    assert await limiter.acquire("b", limit=1, window_s=60)


async def test_metrics_snapshot_is_denatured():
    metrics = Metrics()
    metrics.inc("chat_runs_total")
    metrics.observe("run_latency_ms", 10)
    metrics.observe("run_latency_ms", 30)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["chat_runs_total"] == 1
    assert snapshot["latency_ms"]["run_latency_ms"]["p50"] == 10


async def test_local_object_storage_roundtrip(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    ref = await storage.put("ws-1", b"medical-doc", content_type="application/pdf")
    assert ref.workspace_id == "ws-1"
    assert await storage.get(ref) == b"medical-doc"
    with pytest.raises(FileNotFoundError):
        await storage.get(ObjectRef(workspace_id="ws-1", key="missing"))
