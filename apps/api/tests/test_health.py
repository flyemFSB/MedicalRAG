"""API 健康检查（recipe §1.8：liveness 存活；readiness 依赖降级非失败）。

Qdrant/Redis 走 fake 或拒绝端口，避免真实连接超时拖慢 PR 反馈。
session_store 走内存，跳过 lifespan 对 Redis 的 ping。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_infra.auth.sessions import InMemorySessionStore


class _FakeQdrant:
    """只实现 readiness / lifespan 用到的两个方法。"""

    def __init__(self, *, reachable: bool) -> None:
        self._reachable = reachable

    def get_collections(self):
        if not self._reachable:
            raise ConnectionError("qdrant unreachable")
        return []

    def close(self) -> None:
        pass


@contextmanager
def _app(database_url: str, *, qdrant_reachable: bool = False) -> Iterator[TestClient]:
    """构造带可注入 Qdrant 的 TestClient；monkeypatch 不跨 import 泄漏。"""
    import medicalrag_api.main as main_mod

    original = main_mod.QdrantClient
    main_mod.QdrantClient = lambda **_kw: _FakeQdrant(reachable=qdrant_reachable)  # type: ignore[assignment]
    try:
        app = create_app(
            Settings(
                database_url=database_url,
                redis_url="redis://127.0.0.1:1/0",
                qdrant_url="http://127.0.0.1:1",
                object_root="./.pytest-objects-health",
            ),
            session_store=InMemorySessionStore(),
        )
        with TestClient(app) as client:
            yield client
    finally:
        main_mod.QdrantClient = original


def test_liveness_reports_ok():
    with _app("sqlite+aiosqlite://") as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_healthy_when_dependencies_up():
    # SQLite + 可达 Qdrant + 可 ping Redis → 整体 healthy（就绪契约完整闭环）。

    class _PingRedis:
        async def ping(self) -> bool:
            return True

    with _app("sqlite+aiosqlite://", qdrant_reachable=True) as client:
        client.app.state.redis_available = True
        client.app.state.redis_client = _PingRedis()
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"] == {
        "database": "healthy",
        "redis": "healthy",
        "qdrant": "healthy",
    }
    assert body["status"] == "healthy"


def test_readiness_degraded_when_qdrant_down():
    with _app("sqlite+aiosqlite://", qdrant_reachable=False) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"] == "healthy"
    assert body["checks"]["qdrant"] == "degraded"
    assert body["status"] == "degraded"


def test_readiness_degraded_when_database_down():
    # 依赖不可用返回 degraded（HTTP 200）而非失败；127.0.0.1:1 立即拒绝。
    with _app("postgresql+asyncpg://127.0.0.1:1/none", qdrant_reachable=False) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "degraded"
