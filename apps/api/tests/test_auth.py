"""认证路由检查（register/login/logout/me + __Host- 安全 cookie）。"""

import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_infra.persistence.models import Base


class InMemorySessionStore:
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


def _app(tmp_path):
    db_file = tmp_path / "auth.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    return create_app(
        Settings(database_url=f"sqlite+aiosqlite:///{db_file}"),
        session_store=InMemorySessionStore(),
    )


def test_register_sets_cookie_and_me_returns_user(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        resp = client.post(
            "/api/auth/register", json={"email": "a@example.com", "password": "secret123"}
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "a@example.com"
        assert resp.cookies.get("__Host-SessionID") is not None
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["id"] == resp.json()["id"]


def test_login_wrong_password_returns_401(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        client.post("/api/auth/register", json={"email": "a@example.com", "password": "secret123"})
        resp = client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "wrongpass"}
        )
        assert resp.status_code == 401


def test_duplicate_email_returns_409(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        client.post("/api/auth/register", json={"email": "a@example.com", "password": "secret123"})
        resp = client.post(
            "/api/auth/register", json={"email": "a@example.com", "password": "secret456"}
        )
        assert resp.status_code == 409


def test_logout_revokes_session(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        client.post("/api/auth/register", json={"email": "a@example.com", "password": "secret123"})
        assert client.get("/api/auth/me").status_code == 200
        client.post("/api/auth/logout")
        assert client.get("/api/auth/me").status_code == 401


def test_me_unauthenticated_returns_401(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        assert client.get("/api/auth/me").status_code == 401


def test_cookie_has_secure_attributes(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        resp = client.post(
            "/api/auth/register", json={"email": "a@example.com", "password": "secret123"}
        )
        set_cookie = resp.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert "Secure" in set_cookie
