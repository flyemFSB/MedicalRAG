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


async def test_metrics_renders_counters_and_histograms():
    metrics = Metrics()
    metrics.inc("chat_runs_total")
    metrics.observe("run_latency_ms", 10)
    text = metrics.render_prometheus()
    assert "chat_runs_total" in text
    assert "run_latency_ms_bucket" in text


async def test_metrics_rejects_invalid_names():
    metrics = Metrics()
    with pytest.raises(ValueError):
        metrics.inc("1-bad")


async def test_local_object_storage_roundtrip(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    ref = await storage.put("ws-1", b"medical-doc", content_type="application/pdf")
    assert ref.workspace_id == "ws-1"
    assert await storage.get(ref) == b"medical-doc"
    with pytest.raises(FileNotFoundError):
        await storage.get(ObjectRef(workspace_id="ws-1", key="missing"))
