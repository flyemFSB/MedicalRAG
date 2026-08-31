"""运营管理仓储 SQLite 行为测试（涵盖工作区、知识库、文档、切片、反馈、会话、Outbox 与审计日志）。"""

import uuid

import pytest

from medicalrag_core.audit import AuditEvent
from medicalrag_core.conversation import Conversation, ConversationRef
from medicalrag_core.feedback import Feedback, FeedbackValue
from medicalrag_core.identity.workspace import Role, Workspace, WorkspaceMember
from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document, KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.outbox import OutboxMessage
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base
from medicalrag_infra.persistence.operator import OperatorRepositories


@pytest.fixture
async def repos() -> OperatorRepositories:
    engine, factory = create_engine_and_session_factory("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield OperatorRepositories(factory)
    await engine.dispose()


async def test_workspace_membership_roundtrip(repos: OperatorRepositories):
    workspace = Workspace(id=str(uuid.uuid7()), name="第一人民医院心内科")
    await repos.workspaces.create(workspace)
    assert (await repos.workspaces.get(workspace.id)).name == "第一人民医院心内科"
    user_id = str(uuid.uuid7())
    await repos.memberships.add(
        WorkspaceMember(user_id=user_id, workspace_id=workspace.id, role=Role.OPERATOR)
    )
    memberships = await repos.memberships.memberships_of(user_id)
    assert memberships.is_platform_operator()


async def test_knowledge_base_and_document_roundtrip(repos: OperatorRepositories):
    workspace_id = str(uuid.uuid7())
    kb = KnowledgeBase(id=str(uuid.uuid7()), workspace_id=workspace_id, name="心血管资料")
    created = await repos.knowledge_bases.create(kb)
    assert (await repos.knowledge_bases.get(created.id)).name == "心血管资料"
    document = Document(
        id=str(uuid.uuid7()),
        knowledge_base_id=created.id,
        workspace_id=workspace_id,
        title="中国高血压防治指南.pdf",
        format=".pdf",
        size_bytes=2048,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    doc = await repos.documents.create(document)
    await repos.documents.update_state(doc.id, IngestionRunState.PUBLISHED)
    assert (await repos.documents.get(doc.id)).ingestion_state is IngestionRunState.PUBLISHED


async def test_chunk_repository_insert_and_count(repos: OperatorRepositories):
    document_id = str(uuid.uuid7())
    workspace_id = str(uuid.uuid7())
    chunks = (
        ChunkRecord(
            id=str(uuid.uuid7()),
            document_id=document_id,
            workspace_id=workspace_id,
            text="血压 ≥140/90 mmHg",
            headings=("诊断标准",),
            index=0,
            checksum="abc123",
            token_count=10,
        ),
        ChunkRecord(
            id=str(uuid.uuid7()),
            document_id=document_id,
            workspace_id=workspace_id,
            text="降压目标",
            headings=("降压目标",),
            index=1,
            checksum="def456",
            token_count=8,
        ),
    )
    await repos.chunks.insert_many(chunks)
    assert await repos.chunks.count_for_document(document_id) == 2
    listed = await repos.chunks.list_for_document(document_id)
    assert [c.headings for c in listed] == [("诊断标准",), ("降压目标",)]


async def test_feedback_submit_and_list(repos: OperatorRepositories):
    workspace_id = str(uuid.uuid7())
    await repos.feedback.submit(
        Feedback(
            id=str(uuid.uuid7()),
            message_id=str(uuid.uuid7()),
            conversation_id=str(uuid.uuid7()),
            user_id=str(uuid.uuid7()),
            workspace_id=workspace_id,
            value=FeedbackValue.DISLIKE,
            comment="未直接说明注意事项",
        )
    )
    listed = await repos.feedback.list_for_workspace(workspace_id)
    assert len(listed) == 1
    assert listed[0].value is FeedbackValue.DISLIKE


async def test_conversation_and_thread_mapping(repos: OperatorRepositories):
    conversation = Conversation(
        id=str(uuid.uuid7()),
        user_id=str(uuid.uuid7()),
        workspace_id=str(uuid.uuid7()),
        title="高血压",
    )
    created = await repos.conversations.create(conversation)
    await repos.conversations.save_thread(
        ConversationRef(conversation_id=created.id, thread_id="thread-aegra-1")
    )
    assert await repos.conversations.thread_of(created.id) == "thread-aegra-1"
    listed = await repos.conversations.list_for_user(conversation.user_id)
    assert [c.id for c in listed] == [created.id]


async def test_outbox_claim_and_mark_processed(repos: OperatorRepositories):
    message = OutboxMessage(
        id=str(uuid.uuid7()),
        aggregate_type="ingestion_run",
        aggregate_id="run-1",
        event_type="stage_completed",
        payload={"stage": "indexing"},
    )
    await repos.outbox.append(message)
    claimed = await repos.outbox.claim(10)
    assert [m.id for m in claimed] == [message.id]
    await repos.outbox.mark_processed(message.id)
    assert await repos.outbox.claim(10) == ()


async def test_audit_record_and_list(repos: OperatorRepositories):
    workspace_id = str(uuid.uuid7())
    event = AuditEvent(
        id=str(uuid.uuid7()),
        actor_user_id=str(uuid.uuid7()),
        actor_email="ops@clinic.example",
        workspace_id=workspace_id,
        action="创建",
        entity_type="知识库",
        entity_name="心血管资料",
        detail="新建知识库",
    )
    await repos.audit.record(event)
    listed = await repos.audit.list_for_workspace(workspace_id)
    assert len(listed) == 1
    assert listed[0].entity_type == "知识库"
