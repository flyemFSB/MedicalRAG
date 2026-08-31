"""聊天路由检查（会话认证 + 编排真实持久化 + 注入式 Provider 假件）。"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from medicalrag_api.main import create_app
from medicalrag_api.settings import Settings
from medicalrag_core.chat.model import Analysis
from medicalrag_core.chat.pipeline import ChatPipeline
from medicalrag_core.evidence.evidence import Candidate
from medicalrag_core.evidence.retrieval_policy import RetrievalPolicy
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentTree, ScoredIntent
from medicalrag_infra.auth.sessions import InMemorySessionStore
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.memory import SqlMemory
from medicalrag_infra.persistence.models import Base
from medicalrag_infra.persistence.run_repository import SqlRunRepository

_TREE = IntentTree(
    [
        IntentNode("medical", level=IntentLevel.DOMAIN, kind=IntentKind.KNOWLEDGE, name="医学"),
        IntentNode(
            "disease-info",
            level=IntentLevel.TOPIC,
            parent_id="medical",
            kind=IntentKind.KNOWLEDGE,
            name="疾病信息",
        ),
    ]
)


class FakeClassifier:
    async def analyze(self, request, leaves, context):
        return Analysis(
            rewritten_question=request.question,
            candidates=(ScoredIntent("disease-info", 0.9),),
        )


class FakeRetriever:
    async def retrieve(self, request, queries):
        return (
            Candidate(
                chunk_id="c1",
                document_id="d1",
                source_id="s1",
                title="t",
                snippet="高血压需低盐饮食。",
                intent="disease-info",
                channel="hybrid",
                score=0.9,
            ),
        )


class FakeGenerator:
    async def generate(self, context):
        return "高血压需低盐饮食。"


def _app(tmp_path):
    db_file = tmp_path / "chat.db"
    sync_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    _, factory = create_engine_and_session_factory(f"sqlite+aiosqlite:///{db_file}")
    pipeline = ChatPipeline(
        memory=SqlMemory(factory),
        classifier=FakeClassifier(),
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        runs=SqlRunRepository(factory),
        tree=_TREE,
        retrieval_policy=RetrievalPolicy(version=1, context_cap=8),
    )
    return (
        create_app(
            Settings(database_url=f"sqlite+aiosqlite:///{db_file}"),
            session_store=InMemorySessionStore(),
            chat_pipeline=pipeline,
        ),
        db_file,
    )


def _register(client) -> None:
    client.post("/api/auth/register", json={"email": "a@example.com", "password": "secret123"})


def test_chat_requires_login(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        resp = client.post(
            "/api/chat", json={"question": "q", "conversation_id": str(uuid.uuid7())}
        )
        assert resp.status_code == 401


def test_chat_grounded_path_returns_answer(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _register(client)
        resp = client.post(
            "/api/chat",
            json={"question": "高血压应该注意什么？", "conversation_id": str(uuid.uuid7())},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] == "answered"
        assert body["message"] == "高血压需低盐饮食。"
        assert len(body["evidence"]) == 1
        assert body["evidence"][0]["chunk_id"] == "c1"


def test_chat_persists_run_and_messages(tmp_path):
    app, db_file = _app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _register(client)
        resp = client.post(
            "/api/chat",
            json={"question": "高血压应该注意什么？", "conversation_id": str(uuid.uuid7())},
        )
        assert uuid.UUID(resp.json()["run_id"]).version == 7
    sync_engine = create_engine(f"sqlite:///{db_file}")
    with sync_engine.connect() as conn:
        runs = conn.execute(text("SELECT count(*) FROM chat_runs")).scalar()
        messages = conn.execute(text("SELECT count(*) FROM messages")).scalar()
    assert runs == 1
    assert messages == 2  # 用户 + 助手消息均已持久化


def test_chat_stream_emits_typed_sse_events(tmp_path):
    import json as _json

    app, _ = _app(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        _register(client)
        resp = client.post(
            "/api/chat/stream",
            json={"question": "高血压应该注意什么？", "conversation_id": str(uuid.uuid7())},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names == ["analysis", "evidence", "safety", "token", "done"]
        done = _json.loads(dict(events)["done"])
        assert done["outcome"] == "answered"
        assert done["message"] == "高血压需低盐饮食。"
        assert len(done["evidence"]) == 1


def _parse_sse(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in text.split("\n\n"):
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if name is not None and data is not None:
            events.append((name, data))
    return events
