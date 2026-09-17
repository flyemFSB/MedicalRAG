"""认证路由检查（register/login/logout/me + __Host- 安全 cookie + OPERATOR_EMAILS 提权）。"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_infra.auth.sessions import InMemorySessionStore
from medicalrag_infra.persistence.models import Base

OPERATOR_EMAIL = "ops@clinic.example"


def _app(tmp_path, *, operator_emails: str = ""):
    db_file = tmp_path / "auth.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    return create_app(
        # 显式 cookie_secure：避免宿主 .env 的 MEDICALRAG_COOKIE_SECURE=false 污染 HTTPS cookie 断言
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_file}",
            cookie_secure=True,
            operator_emails=operator_emails,
        ),
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


def test_member_promoted_to_operator_on_login(tmp_path):
    """已是成员的用户命中 OPERATOR_EMAILS 后再登录：原地提权而非重复 INSERT（uq_workspace_member）。"""
    with TestClient(
        _app(tmp_path, operator_emails=OPERATOR_EMAIL), base_url="https://testserver"
    ) as client:
        # 先以普通注册流程建立成员资格（当时邮箱不在名单内 → member）
        client.post("/api/auth/register", json={"email": OPERATOR_EMAIL, "password": "secret123"})
        client.post("/api/auth/logout")
        # 名单生效后重新登录：必须成功且拿到 operator 权限
        resp = client.post(
            "/api/auth/login", json={"email": OPERATOR_EMAIL, "password": "secret123"}
        )
        assert resp.status_code == 200
        assert client.get("/api/admin/knowledge-bases").status_code == 200
