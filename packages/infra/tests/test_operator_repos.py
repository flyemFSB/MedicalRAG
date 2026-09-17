"""运营管理仓储 SQLite 行为测试（涵盖工作区、知识库、文档、分块、反馈、会话、发件箱与审计日志）。"""

import pytest

from medicalrag_core.identity.workspace import Role, Workspace, WorkspaceMember
from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document, KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.records import Conversation, Feedback, FeedbackValue, OutboxMessage
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.models import Base
from medicalrag_infra.persistence.operator import OperatorRepositories


@pytest.fixture
async def repos(persistence_url: str) -> OperatorRepositories:
    engine, factory = create_engine_and_session_factory(persistence_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield OperatorRepositories(factory)
    await engine.dispose()


async def test_workspace_membership_roundtrip(repos: OperatorRepositories):
    workspace = Workspace(id=str(uuid7()), name="第一人民医院心内科")
    await repos.workspaces.create(workspace)
    listed = await repos.workspaces.list_all_with_members()
    assert any(ws.id == workspace.id and ws.name == workspace.name for ws, _ in listed)
    user_id = str(uuid7())
    await repos.memberships.add(
        WorkspaceMember(user_id=user_id, workspace_id=workspace.id, role=Role.OPERATOR)
    )
    memberships = await repos.memberships.memberships_of(user_id)
    assert memberships.is_platform_operator()


async def test_knowledge_base_and_document_roundtrip(repos: OperatorRepositories):
    workspace_id = str(uuid7())
    kb = KnowledgeBase(id=str(uuid7()), workspace_id=workspace_id, name="心血管资料")
    created = await repos.knowledge_bases.create(kb)
    assert (await repos.knowledge_bases.get(created.id)).name == "心血管资料"
    document = Document(
        id=str(uuid7()),
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
    document_id = str(uuid7())
    workspace_id = str(uuid7())
    chunks = (
        ChunkRecord(
            id=str(uuid7()),
            document_id=document_id,
            workspace_id=workspace_id,
            text="血压 ≥140/90 mmHg",
            headings=("诊断标准",),
            index=0,
            checksum="abc123",
            token_count=10,
        ),
        ChunkRecord(
            id=str(uuid7()),
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
    workspace_id = str(uuid7())
    await repos.feedback.submit(
        Feedback(
            id=str(uuid7()),
            message_id=str(uuid7()),
            conversation_id=str(uuid7()),
            user_id=str(uuid7()),
            workspace_id=workspace_id,
            value=FeedbackValue.DISLIKE,
            comment="未直接说明注意事项",
        )
    )
    listed = await repos.feedback.list_all()
    assert len(listed) == 1
    assert listed[0].value is FeedbackValue.DISLIKE


async def test_conversation_list(repos: OperatorRepositories):
    conversation = Conversation(
        id=str(uuid7()),
        user_id=str(uuid7()),
        workspace_id=str(uuid7()),
        title="高血压",
    )
    created = await repos.conversations.create(conversation)
    listed = await repos.conversations.list_for_user(conversation.user_id)
    assert [c.id for c in listed] == [created.id]


async def test_outbox_claim_and_mark_processed(repos: OperatorRepositories):
    message = OutboxMessage(
        id=str(uuid7()),
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


async def test_outbox_claim_respects_max_attempts_poison_isolation(repos: OperatorRepositories):
    """毒消息隔离：attempts 达到 max_attempts 后 claim 跳过该消息（保持未处理、可追溯）。"""
    message = OutboxMessage(
        id=str(uuid7()),
        aggregate_type="ingestion_run",
        aggregate_id="run-1",
        event_type="ingestion.stage",
        payload={"stage": "extracting"},
    )
    await repos.outbox.append(message)
    claimed = await repos.outbox.claim(10, max_attempts=3)
    assert len(claimed) == 1
    for _ in range(3):
        await repos.outbox.record_failure(message.id)
    # 达到上限：不再领取（毒消息隔离）
    assert await repos.outbox.claim(10, max_attempts=3) == ()
    # 无 max_attempts 的查询仍可见（保持可追溯，供运营排查）
    still_there = await repos.outbox.claim(10)
    assert [m.id for m in still_there] == [message.id]


async def test_outbox_record_failure_releases_lease_for_next_poll(repos: OperatorRepositories):
    """投递失败后立即释放租约：下个 relay 轮询即可重投，而非等满 lease_s。"""
    message = OutboxMessage(
        id=str(uuid7()),
        aggregate_type="ingestion_run",
        aggregate_id="run-1",
        event_type="ingestion.stage",
        payload={"stage": "extracting"},
    )
    await repos.outbox.append(message)
    assert len(await repos.outbox.claim(10)) == 1
    await repos.outbox.record_failure(message.id)
    # claimed_at 已清除：即使租约（默认 300s）远未到期，下个周期也能重新领取
    assert len(await repos.outbox.claim(10)) == 1


async def test_document_delete_removes_stage_rows_under_fk_enforcement(
    repos: OperatorRepositories,
):
    """回归（P0）：删除文档必须级联清理 IngestionRunStage——外键无 ON DELETE CASCADE，
    遗漏该步在 PG 上删除任何完成过阶段的文档必失败（fixture 已全局开启 SQLite FK pragma）。"""
    workspace_id = str(uuid7())
    kb = await repos.knowledge_bases.create(
        KnowledgeBase(id=str(uuid7()), workspace_id=workspace_id, name="回归测试库")
    )
    document = await repos.documents.create(
        Document(
            id=str(uuid7()),
            knowledge_base_id=kb.id,
            workspace_id=workspace_id,
            title="指南.md",
            format=".md",
            size_bytes=64,
            ingestion_state=IngestionRunState.PUBLISHED,
        )
    )
    # 完成一次阶段推进以产生 IngestionRunStage 行（阶段唯一约束按 (run_id, stage) 记录）
    run_id = await repos.ingestion.create_run(document.id, workspace_id)
    await repos.ingestion.complete_stage(run_id, IngestionRunState.ACCEPTED)
    assert await repos.documents.get(document.id) is not None

    await repos.documents.delete(document.id)
    assert await repos.documents.get(document.id) is None
