"""上传路由检查（格式白名单 / 大小上限 / 越权拒绝 / outbox 写入；文件摄取安全边界的回归网）。

文件上传是外部输入进入系统的第一道信任边界：此前的空白意味着 415/413/404 拒绝路径
与 outbox 事务写入完全没有回归保护。
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_infra.auth.sessions import InMemorySessionStore

OPERATOR_EMAIL = "op@example.com"


def _create_app(tmp_path):
    db_file = tmp_path / "upload.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    from medicalrag_infra.persistence.models import Base

    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    return create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{db_file}",
            operator_emails=OPERATOR_EMAIL,
            object_root=str(tmp_path / "objects"),
        ),
        session_store=InMemorySessionStore(),
    )


def _login(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register", json={"email": OPERATOR_EMAIL, "password": "secret123"}
    )
    assert resp.status_code == 201


def _create_kb(client: TestClient) -> str:
    resp = client.post("/api/admin/knowledge-bases", json={"name": "心血管资料"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_upload_requires_login(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": "00000000-0000-7fff-ffff-ffffffffffff"},
            files={"file": ("guide.md", b"# content", "text/markdown")},
        )
        assert resp.status_code == 401


def test_upload_rejects_unsupported_format(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        kb_id = _create_kb(client)
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("payload.exe", b"MZ...", "application/octet-stream")},
        )
        assert resp.status_code == 415


def test_upload_rejects_oversized_file(tmp_path, monkeypatch):
    import medicalrag_api.api.upload as upload_module

    monkeypatch.setattr(upload_module, "MAX_UPLOAD_BYTES", 10)
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        kb_id = _create_kb(client)
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("guide.md", b"x" * 20, "text/markdown")},
        )
        assert resp.status_code == 413


def test_upload_rejects_foreign_knowledge_base(tmp_path):
    """越权知识库一律 404（防存在性泄露），且先于落盘（不产生孤儿对象）。"""
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": str(uuid.uuid4())},
            files={"file": ("guide.md", b"# content", "text/markdown")},
        )
        assert resp.status_code == 404


def test_upload_rejects_format_masquerade(tmp_path):
    """字节级嗅探（ADR 0087）：扩展名声称 PDF 但字节内容不符 → 415（防扩展名伪装）。"""
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        kb_id = _create_kb(client)
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("guide.pdf", b"just text, definitely not a pdf", "application/pdf")},
        )
        assert resp.status_code == 415


def test_upload_accepts_supported_format_and_enqueues(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        kb_id = _create_kb(client)
        resp = client.post(
            "/api/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("guide.md", "# 高血压\n低盐饮食。".encode(), "text/markdown")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "guide.md"
        assert uuid.UUID(body["document_id"]).version == 7
        assert uuid.UUID(body["run_id"]).version == 7

    # 事务性 Outbox：Document / IngestionRun / Outbox 事件同事务落库
    sync_engine = create_engine(f"sqlite:///{tmp_path / 'upload.db'}")
    with sync_engine.connect() as conn:
        document = conn.execute(text("SELECT title, ingestion_state FROM documents")).one()
        outbox = conn.execute(
            text("SELECT event_type, payload FROM outbox ORDER BY created_at DESC LIMIT 1")
        ).one()
    assert document == ("guide.md", "accepted")
    assert outbox[0] == "ingestion.stage"
    assert '"stage": "accepted"' in str(outbox[1])
    sync_engine.dispose()
