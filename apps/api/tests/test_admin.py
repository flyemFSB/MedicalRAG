"""运营控制台 API 检查（operator 授权 + 知识库/意图树/追踪/反馈数据面）。"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_core.ids import uuid7
from medicalrag_infra.auth.sessions import InMemorySessionStore
from medicalrag_infra.persistence.models import Base

OPERATOR_EMAIL = "ops@clinic.example"
MEMBER_EMAIL = "doc@clinic.example"


def _app(tmp_path, *, operator_emails: str = OPERATOR_EMAIL):
    db_file = tmp_path / "admin.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    return create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_file}",
            operator_emails=operator_emails,
            object_root=str(tmp_path / "objects"),
        ),
        session_store=InMemorySessionStore(),
    )


def _login(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": "secret123"})


def test_admin_requires_operator(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        _login(client, MEMBER_EMAIL)
        resp = client.get("/api/admin/knowledge-bases")
        assert resp.status_code == 403  # member 无权访问运营端点


def test_operator_crud_knowledge_bases(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        _login(client, OPERATOR_EMAIL)
        created = client.post(
            "/api/admin/knowledge-bases",
            json={"name": "心血管资料", "description": "循证资料"},
        )
        assert created.status_code == 201
        kb = created.json()
        assert kb["name"] == "心血管资料"
        listed = client.get("/api/admin/knowledge-bases")
        assert listed.status_code == 200
        assert any(item["id"] == kb["id"] for item in listed.json())


def test_intent_tree_and_dashboard_read(tmp_path):
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        _login(client, OPERATOR_EMAIL)
        tree = client.get("/api/admin/intent-tree")
        assert tree.status_code == 200
        assert isinstance(tree.json(), list)
        dashboard = client.get("/api/admin/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["total_chats"] == 0


def test_conversations_and_feedback_for_member(tmp_path):

    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        _login(client, MEMBER_EMAIL)
        conv = client.post("/api/conversations", json={"title": "高血压"})
        assert conv.status_code == 201
        conversation_id = conv.json()["id"]
        listed = client.get("/api/conversations")
        assert listed.status_code == 200
        assert any(c["id"] == conversation_id for c in listed.json())
        feedback = client.post(
            "/api/feedback",
            json={
                "message_id": str(uuid7()),
                "conversation_id": conversation_id,
                "value": "like",
            },
        )
        assert feedback.status_code == 201


def test_feedback_rejects_foreign_conversation(tmp_path):
    """对象级越权写（OWASP API1）：不得对他人的会话写反馈。"""
    with TestClient(_app(tmp_path), base_url="https://testserver") as client:
        _login(client, MEMBER_EMAIL)
        conversation_id = client.post("/api/conversations", json={"title": "mine"}).json()["id"]

        client.cookies.clear()
        _login(client, "intruder@clinic.example")
        resp = client.post(
            "/api/feedback",
            json={
                "message_id": str(uuid7()),
                "conversation_id": conversation_id,
                "value": "like",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "会话不存在"
