"""API 健康检查（recipe §1.8：liveness 存活；readiness 依赖降级非失败）。"""

from fastapi.testclient import TestClient

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings


def test_liveness_reports_ok():
    app = create_app(Settings(database_url="sqlite+aiosqlite://"))
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_healthy_when_database_up():
    # 数据库可达为 healthy；本测试环境无 Redis/Qdrant，整体按依赖实际状态 degraded。
    app = create_app(Settings(database_url="sqlite+aiosqlite://"))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"] == "healthy"
    assert "redis" in body["checks"]
    assert "qdrant" in body["checks"]


def test_readiness_degraded_when_database_down():
    # 依赖不可用返回 degraded（HTTP 200）而非失败；localhost 无服务立即拒绝，避免挂起。
    app = create_app(Settings(database_url="postgresql+asyncpg://localhost:1/none"))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "degraded"
