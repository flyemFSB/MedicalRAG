"""运营管理后台持久化仓储实现：实现 medical-core 定义的各项仓储协议端口及统计/追踪读面查询。

对应产品规范「运营后台」数据持久化层：包括工作区与成员资格、知识库/文档/切片、摄取作业运行、用户反馈、业务会话、
模型目标与凭据、事务性 Outbox、操作审计、推荐样例问题、医学术语映射、以及管理看板与性能度量指标。
所有业务实体主键均严格遵循 ADR 0066 规范采用 uuid7。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.audit import AuditEvent
from medicalrag_core.conversation import Conversation, ConversationRef
from medicalrag_core.feedback import Feedback, FeedbackValue
from medicalrag_core.identity.workspace import (
    Role,
    UserMemberships,
    Workspace,
    WorkspaceMember,
)
from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document, KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.model_router.model import CircuitState, ModelTarget
from medicalrag_core.outbox import OutboxMessage

from .ingestion import SqlIngestionRunRepository
from .models import (
    AuditEventRow,
    ChatRun,
    ChunkRow,
    ConversationRow,
    DocumentRow,
    FeedbackRow,
    IngestionRun,
    IngestionRunStage,
    KnowledgeBaseRow,
    Message,
    ModelTargetRow,
    OutboxRow,
    PlatformCredentialRow,
    QueryTermMappingRow,
    SampleQuestionRow,
    User,
    WorkspaceMemberRow,
    WorkspaceRow,
)

_utcnow = lambda: datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return str(value) if value is not None else None


def _kb_from_row(row: KnowledgeBaseRow) -> KnowledgeBase:
    return KnowledgeBase(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        name=row.name,
        description=row.description,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _doc_from_row(row: DocumentRow) -> Document:
    return Document(
        id=str(row.id),
        knowledge_base_id=str(row.knowledge_base_id),
        workspace_id=str(row.workspace_id),
        title=row.title,
        format=row.format,
        size_bytes=row.size_bytes,
        ingestion_state=IngestionRunState(row.ingestion_state),
        chunk_count=row.chunk_count,
        published=row.published,
        created_at=_iso(row.created_at),
    )


def _conversation_from_row(row: ConversationRow) -> Conversation:
    return Conversation(
        id=str(row.id),
        user_id=str(row.user_id),
        workspace_id=str(row.workspace_id),
        title=row.title,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


class SqlWorkspaceRepository:
    """工作区持久化仓储：实现 medical_core.identity.workspace.WorkspaceRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, workspace: Workspace) -> None:
        async with self._sessions() as session:
            session.add(WorkspaceRow(id=uuid.UUID(workspace.id), name=workspace.name))
            await session.commit()

    async def get(self, workspace_id: str) -> Workspace | None:
        async with self._sessions() as session:
            row = await session.get(WorkspaceRow, uuid.UUID(workspace_id))
            if row is None:
                return None
            return Workspace(id=str(row.id), name=row.name, created_at=str(row.created_at))

    async def list_members(self, workspace_id: str) -> tuple[WorkspaceMember, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(WorkspaceMemberRow).where(
                        WorkspaceMemberRow.workspace_id == uuid.UUID(workspace_id)
                    )
                )
            ).all()
            return tuple(
                WorkspaceMember(
                    user_id=str(r.user_id), workspace_id=str(r.workspace_id), role=Role(r.role)
                )
                for r in rows
            )

    async def list_all_with_members(self) -> tuple[tuple[Workspace, int], ...]:
        """运营管理控制台：查询全量工作区列表及其对应的成员数量统计。"""
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(WorkspaceRow).order_by(WorkspaceRow.created_at))
            ).all()
            out: list[tuple[Workspace, int]] = []
            for row in rows:
                count = len(
                    (
                        await session.scalars(
                            select(WorkspaceMemberRow).where(
                                WorkspaceMemberRow.workspace_id == row.id
                            )
                        )
                    ).all()
                )
                out.append(
                    (
                        Workspace(id=str(row.id), name=row.name, created_at=str(row.created_at)),
                        count,
                    )
                )
            return tuple(out)


class SqlMembershipRepository:
    """工作区成员资格持久化仓储：实现 MembershipRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, member: WorkspaceMember) -> None:
        async with self._sessions() as session:
            session.add(
                WorkspaceMemberRow(
                    user_id=uuid.UUID(member.user_id),
                    workspace_id=uuid.UUID(member.workspace_id),
                    role=member.role.value,
                )
            )
            await session.commit()

    async def memberships_of(self, user_id: str) -> UserMemberships:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(WorkspaceMemberRow).where(
                        WorkspaceMemberRow.user_id == uuid.UUID(user_id)
                    )
                )
            ).all()
            return UserMemberships(
                user_id=user_id,
                memberships=tuple(
                    WorkspaceMember(
                        user_id=str(r.user_id),
                        workspace_id=str(r.workspace_id),
                        role=Role(r.role),
                    )
                    for r in rows
                ),
            )

    async def remove(self, user_id: str, workspace_id: str) -> None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(WorkspaceMemberRow).where(
                    WorkspaceMemberRow.user_id == uuid.UUID(user_id),
                    WorkspaceMemberRow.workspace_id == uuid.UUID(workspace_id),
                )
            )
            if row is not None:
                await session.delete(row)
                await session.commit()


class SqlKnowledgeBaseRepository:
    """知识库持久化仓储：实现 KnowledgeBaseRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        async with self._sessions() as session:
            row = KnowledgeBaseRow(
                id=uuid.UUID(kb.id),
                workspace_id=uuid.UUID(kb.workspace_id),
                name=kb.name,
                description=kb.description,
            )
            session.add(row)
            await session.commit()
            return _kb_from_row(row)

    async def get(self, kb_id: str) -> KnowledgeBase | None:
        async with self._sessions() as session:
            row = await session.get(KnowledgeBaseRow, uuid.UUID(kb_id))
            if row is None:
                return None
            return _kb_from_row(row)

    async def list_for_workspace(self, workspace_id: str) -> tuple[KnowledgeBase, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(KnowledgeBaseRow)
                    .where(KnowledgeBaseRow.workspace_id == uuid.UUID(workspace_id))
                    .order_by(KnowledgeBaseRow.created_at)
                )
            ).all()
            return tuple(_kb_from_row(r) for r in rows)


class SqlDocumentRepository:
    """文档持久化仓储：实现 DocumentRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, document: Document) -> Document:
        async with self._sessions() as session:
            row = DocumentRow(
                id=uuid.UUID(document.id),
                knowledge_base_id=uuid.UUID(document.knowledge_base_id),
                workspace_id=uuid.UUID(document.workspace_id),
                title=document.title,
                format=document.format,
                size_bytes=document.size_bytes,
                ingestion_state=document.ingestion_state.value,
                chunk_count=document.chunk_count,
                published=document.published,
            )
            session.add(row)
            await session.commit()
            return _doc_from_row(row)

    async def get(self, document_id: str) -> Document | None:
        async with self._sessions() as session:
            row = await session.get(DocumentRow, uuid.UUID(document_id))
            if row is None:
                return None
            return _doc_from_row(row)

    async def list_for_knowledge_base(self, kb_id: str) -> tuple[Document, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(DocumentRow)
                    .where(DocumentRow.knowledge_base_id == uuid.UUID(kb_id))
                    .order_by(DocumentRow.created_at)
                )
            ).all()
            return tuple(_doc_from_row(r) for r in rows)

    async def update_state(self, document_id: str, state: IngestionRunState) -> None:
        async with self._sessions() as session:
            row = await session.get(DocumentRow, uuid.UUID(document_id))
            if row is None:
                raise KeyError(f"document 不存在: {document_id}")
            row.ingestion_state = state.value
            await session.commit()

    async def set_published(self, document_id: str, published: bool) -> None:
        async with self._sessions() as session:
            row = await session.get(DocumentRow, uuid.UUID(document_id))
            if row is None:
                raise KeyError(f"document 不存在: {document_id}")
            row.published = published
            await session.commit()

    async def delete(self, document_id: str) -> None:
        """删除指定的文档实体及其关联的全部切片数据（Qdrant 向量点由 Worker 异步优先级联清理，ADR 0079）。"""
        doc_id = uuid.UUID(document_id)
        async with self._sessions() as session:
            await session.execute(delete(ChunkRow).where(ChunkRow.document_id == doc_id))
            await session.execute(delete(DocumentRow).where(DocumentRow.id == doc_id))
            await session.commit()

    async def list_ids(self) -> tuple[str, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(select(DocumentRow.id))
            return tuple(str(r) for r in rows.all())

    async def counts_by_kb(self, workspace_id: str) -> dict[str, int]:
        """单次聚合统计工作区下各知识库包含的文档数量（消除 N+1 查询，供管理后台列表渲染）。"""
        async with self._sessions() as session:
            rows = await session.execute(
                select(DocumentRow.knowledge_base_id, func.count())
                .where(DocumentRow.workspace_id == uuid.UUID(workspace_id))
                .group_by(DocumentRow.knowledge_base_id)
            )
            return {str(kb_id): int(count) for kb_id, count in rows.all()}


class SqlChunkRepository:
    """文档切片持久化仓储：实现 ChunkRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def insert_many(self, chunks: tuple[ChunkRecord, ...]) -> None:
        async with self._sessions() as session:
            for chunk in chunks:
                session.add(
                    ChunkRow(
                        id=uuid.UUID(chunk.id),
                        document_id=uuid.UUID(chunk.document_id),
                        workspace_id=uuid.UUID(chunk.workspace_id),
                        text=chunk.text,
                        headings=list(chunk.headings),
                        index=chunk.index,
                        checksum=chunk.checksum,
                        token_count=chunk.token_count,
                        page_ref=chunk.page_ref,
                    )
                )
            await session.commit()

    async def list_for_document(self, document_id: str) -> tuple[ChunkRecord, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ChunkRow)
                    .where(ChunkRow.document_id == uuid.UUID(document_id))
                    .order_by(ChunkRow.index)
                )
            ).all()
            return tuple(
                ChunkRecord(
                    id=str(r.id),
                    document_id=str(r.document_id),
                    workspace_id=str(r.workspace_id),
                    text=r.text,
                    headings=tuple(r.headings or []),
                    index=r.index,
                    checksum=r.checksum,
                    token_count=r.token_count,
                    page_ref=r.page_ref,
                    created_at=str(r.created_at),
                )
                for r in rows
            )

    async def count_for_document(self, document_id: str) -> int:
        async with self._sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(ChunkRow)
                    .where(ChunkRow.document_id == uuid.UUID(document_id))
                )
                or 0
            )


class SqlFeedbackRepository:
    """用户反馈持久化仓储：实现 FeedbackRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def submit(self, feedback: Feedback) -> None:
        async with self._sessions() as session:
            session.add(
                FeedbackRow(
                    id=uuid.UUID(feedback.id),
                    message_id=uuid.UUID(feedback.message_id),
                    conversation_id=uuid.UUID(feedback.conversation_id),
                    user_id=uuid.UUID(feedback.user_id),
                    workspace_id=uuid.UUID(feedback.workspace_id),
                    value=feedback.value.value,
                    comment=feedback.comment,
                )
            )
            await session.commit()

    async def list_for_workspace(self, workspace_id: str) -> tuple[Feedback, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(FeedbackRow)
                    .where(FeedbackRow.workspace_id == uuid.UUID(workspace_id))
                    .order_by(FeedbackRow.created_at.desc())
                )
            ).all()
            return tuple(
                Feedback(
                    id=str(r.id),
                    message_id=str(r.message_id),
                    conversation_id=str(r.conversation_id),
                    user_id=str(r.user_id),
                    workspace_id=str(r.workspace_id),
                    value=FeedbackValue(r.value),
                    comment=r.comment,
                    created_at=str(r.created_at),
                )
                for r in rows
            )


class SqlConversationRepository:
    """业务会话持久化仓储（包含业务会话与 Aegra 运行时上下文 Thread 的映射管理，ADR 0002）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sessions() as session:
            row = ConversationRow(
                id=uuid.UUID(conversation.id),
                user_id=uuid.UUID(conversation.user_id),
                workspace_id=uuid.UUID(conversation.workspace_id),
                title=conversation.title,
            )
            session.add(row)
            await session.commit()
            return _conversation_from_row(row)

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._sessions() as session:
            row = await session.get(ConversationRow, uuid.UUID(conversation_id))
            if row is None:
                return None
            return _conversation_from_row(row)

    async def list_for_user(self, user_id: str) -> tuple[Conversation, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ConversationRow)
                    .where(ConversationRow.user_id == uuid.UUID(user_id))
                    .order_by(ConversationRow.updated_at.desc())
                )
            ).all()
            return tuple(_conversation_from_row(r) for r in rows)

    async def touch(self, conversation_id: str) -> None:
        async with self._sessions() as session:
            row = await session.get(ConversationRow, uuid.UUID(conversation_id))
            if row is not None:
                row.updated_at = _utcnow()
                await session.commit()

    async def save_thread(self, ref: ConversationRef) -> None:
        async with self._sessions() as session:
            row = await session.get(ConversationRow, uuid.UUID(ref.conversation_id))
            if row is not None:
                row.thread_id = ref.thread_id
                await session.commit()

    async def thread_of(self, conversation_id: str) -> str | None:
        async with self._sessions() as session:
            row = await session.get(ConversationRow, uuid.UUID(conversation_id))
            return row.thread_id if row is not None else None


class SqlModelTargetRepository:
    """模型目标与熔断状态持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_all(self) -> tuple[ModelTarget, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ModelTargetRow).order_by(ModelTargetRow.priority.desc())
                )
            ).all()
            return tuple(
                ModelTarget(
                    id=str(r.id),
                    name=r.name,
                    provider=r.provider,
                    model=r.model,
                    capabilities=frozenset(r.capabilities or []),
                    priority=r.priority,
                    circuit=CircuitState(r.circuit_state),
                    failures=r.failures,
                )
                for r in rows
            )

    async def save(self, target: ModelTarget) -> None:
        async with self._sessions() as session:
            row = await session.get(ModelTargetRow, uuid.UUID(target.id))
            if row is None:
                session.add(
                    ModelTargetRow(
                        id=uuid.UUID(target.id),
                        name=target.name,
                        provider=target.provider,
                        model=target.model,
                        capabilities=list(target.capabilities),
                        priority=target.priority,
                        circuit_state=target.circuit.value,
                        failures=target.failures,
                    )
                )
            else:
                row.name = target.name
                row.provider = target.provider
                row.model = target.model
                row.capabilities = list(target.capabilities)
                row.priority = target.priority
                row.circuit_state = target.circuit.value
                row.failures = target.failures
            await session.commit()


class SqlOutboxRepository:
    """事务性 Outbox 持久化仓储（采用 SKIP LOCKED 避免并发冲突；具体 Relay 投递见 worker）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, message: OutboxMessage) -> None:
        async with self._sessions() as session:
            session.add(
                OutboxRow(
                    id=uuid.UUID(message.id),
                    aggregate_type=message.aggregate_type,
                    aggregate_id=message.aggregate_id,
                    event_type=message.event_type,
                    payload=dict(message.payload),
                )
            )
            await session.commit()

    async def claim(
        self, limit: int, *, max_attempts: int | None = None
    ) -> tuple[OutboxMessage, ...]:
        async with self._sessions() as session:
            query = (
                select(OutboxRow)
                .where(OutboxRow.processed_at.is_(None))
                .order_by(OutboxRow.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            if max_attempts is not None:
                query = query.where(OutboxRow.attempts < max_attempts)
            rows = (await session.scalars(query)).all()
            return tuple(
                OutboxMessage(
                    id=str(r.id),
                    aggregate_type=r.aggregate_type,
                    aggregate_id=r.aggregate_id,
                    event_type=r.event_type,
                    payload=dict(r.payload or {}),
                    created_at=str(r.created_at),
                    processed_at=str(r.processed_at) if r.processed_at else None,
                    attempts=r.attempts,
                )
                for r in rows
            )

    async def mark_processed(self, message_id: str) -> None:
        async with self._sessions() as session:
            row = await session.get(OutboxRow, uuid.UUID(message_id))
            if row is not None:
                row.processed_at = _utcnow()
                await session.commit()

    async def record_failure(self, message_id: str) -> None:
        """记录投递失败并将重试次数 +1；超过最大重试上限的消息将在 claim 阶段自动跳过（ADR 0080 保障毒消息可追溯）。"""
        async with self._sessions() as session:
            row = await session.get(OutboxRow, uuid.UUID(message_id))
            if row is not None:
                row.attempts += 1
                await session.commit()


class SqlAuditRepository:
    """操作审计持久化仓储：实现 AuditRepository 协议端口。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, event: AuditEvent) -> None:
        async with self._sessions() as session:
            session.add(
                AuditEventRow(
                    id=uuid.UUID(event.id),
                    actor_user_id=uuid.UUID(event.actor_user_id),
                    actor_email=event.actor_email,
                    workspace_id=uuid.UUID(event.workspace_id),
                    action=event.action,
                    entity_type=event.entity_type,
                    entity_name=event.entity_name,
                    detail=event.detail,
                )
            )
            await session.commit()

    async def list_for_workspace(self, workspace_id: str) -> tuple[AuditEvent, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(AuditEventRow)
                    .where(AuditEventRow.workspace_id == uuid.UUID(workspace_id))
                    .order_by(AuditEventRow.created_at.desc())
                )
            ).all()
            return tuple(
                AuditEvent(
                    id=str(r.id),
                    actor_user_id=str(r.actor_user_id),
                    actor_email=r.actor_email,
                    workspace_id=str(r.workspace_id),
                    action=r.action,
                    entity_type=r.entity_type,
                    entity_name=r.entity_name,
                    detail=r.detail,
                    created_at=str(r.created_at),
                )
                for r in rows
            )


class SqlRunListingRepository:
    """聊天运行记录追踪与管理看板聚合查询仓储（跨 chat_runs / messages / conversations 表进行只读查询）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def recent_runs(self, workspace_id: str, limit: int = 50) -> tuple[ChatRun, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ChatRun)
                    .where(ChatRun.workspace_id == uuid.UUID(workspace_id))
                    .order_by(ChatRun.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return tuple(rows)

    async def question_count(self, workspace_id: str) -> int:
        async with self._sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(
                        Message.workspace_id == uuid.UUID(workspace_id),
                        Message.role == "user",
                    )
                )
                or 0
            )

    async def conversation_count(self, workspace_id: str) -> int:
        async with self._sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(ConversationRow)
                    .where(ConversationRow.workspace_id == uuid.UUID(workspace_id))
                )
                or 0
            )

    async def avg_latency_ms(self, workspace_id: str) -> float:
        async with self._sessions() as session:
            runs = (
                await session.scalars(
                    select(ChatRun).where(ChatRun.workspace_id == uuid.UUID(workspace_id))
                )
            ).all()
            latencies = [
                (r.completed_at - r.created_at).total_seconds() * 1000
                for r in runs
                if r.completed_at is not None and r.created_at is not None
            ]
            return round(sum(latencies) / len(latencies), 1) if latencies else 0.0

    async def published_docs(self, workspace_id: str) -> int:
        async with self._sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentRow)
                    .where(
                        DocumentRow.workspace_id == uuid.UUID(workspace_id),
                        DocumentRow.ingestion_state == IngestionRunState.PUBLISHED.value,
                    )
                )
                or 0
            )

    async def failed_runs(self, workspace_id: str) -> int:
        async with self._sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(IngestionRun)
                    .where(
                        IngestionRun.workspace_id == uuid.UUID(workspace_id),
                        IngestionRun.state == IngestionRunState.FAILED.value,
                    )
                )
                or 0
            )


class SqlQueryTermMappingRepository:
    """医学专业术语与意图节点映射持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_all(self) -> tuple[QueryTermMappingRow, ...]:
        async with self._sessions() as session:
            return tuple(
                (
                    await session.scalars(
                        select(QueryTermMappingRow).order_by(QueryTermMappingRow.created_at)
                    )
                ).all()
            )

    async def add(self, term: str, intent_node_id: str) -> None:
        async with self._sessions() as session:
            session.add(QueryTermMappingRow(term=term, intent_node_id=intent_node_id, enabled=True))
            await session.commit()


class SqlCredentialRepository:
    """平台级模型凭据持久化仓储（严禁明文存储密钥本体，仅存储服务商元数据与连通性测试结果）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_all(self) -> tuple[PlatformCredentialRow, ...]:
        async with self._sessions() as session:
            return tuple(
                (
                    await session.scalars(
                        select(PlatformCredentialRow).order_by(PlatformCredentialRow.created_at)
                    )
                ).all()
            )


class SqlAdminUserRepository:
    """管理后台用户账户查询仓储（password_hash 密码哈希绝不向外暴露）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_for_admin(self) -> tuple[dict[str, object], ...]:
        async with self._sessions() as session:
            rows = (await session.scalars(select(User).order_by(User.created_at))).all()
            return tuple(
                {
                    "id": str(row.id),
                    "email": row.email,
                    "status": "active",
                    "created_at": str(row.created_at) if row.created_at else None,
                }
                for row in rows
            )


class SqlSampleQuestionRepository:
    """推荐样例问题配置持久化仓储。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_for_workspace(self, workspace_id: str) -> tuple[dict[str, object], ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(SampleQuestionRow)
                    .where(SampleQuestionRow.workspace_id == uuid.UUID(workspace_id))
                    .order_by(SampleQuestionRow.created_at)
                )
            ).all()
            return tuple(
                {
                    "id": str(row.id),
                    "text": row.text,
                    "intent_node_id": row.intent_node_id,
                    "enabled": row.enabled,
                    "created_at": str(row.created_at) if row.created_at else None,
                }
                for row in rows
            )


class SqlIngestionRunListing:
    """文档摄取运行管理读面仓储：支持按工作区查询摄取作业执行历史（包含关联文档标题及各阶段状态）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def object_key_for_document(self, document_id: str) -> str | None:
        """获取指定文档最新一次摄取运行的对象存储 Key（供文件预览与下载使用，ADR 0033）。"""
        async with self._sessions() as session:
            run = await session.scalar(
                select(IngestionRun)
                .where(IngestionRun.document_id == uuid.UUID(document_id))
                .order_by(IngestionRun.created_at.desc())
                .limit(1)
            )
            if run is None:
                return None
            return str((run.data or {}).get("object_key", "")) or None

    async def list_for_workspace(self, workspace_id: str) -> tuple[dict[str, object], ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(IngestionRun)
                    .where(IngestionRun.workspace_id == uuid.UUID(workspace_id))
                    .order_by(IngestionRun.created_at.desc())
                )
            ).all()
            out: list[dict[str, object]] = []
            for run in rows:
                document = await session.get(DocumentRow, run.document_id)
                stage_rows = (
                    await session.scalars(
                        select(IngestionRunStage).where(IngestionRunStage.run_id == run.id)
                    )
                ).all()
                out.append(
                    {
                        "id": str(run.id),
                        "document_title": document.title if document else str(run.document_id),
                        "status": run.state,
                        "stages": [
                            {"name": s.stage, "label": s.stage, "status": "succeeded"}
                            for s in stage_rows
                        ],
                        "started_at": str(run.created_at) if run.created_at else None,
                    }
                )
            return tuple(out)


class OperatorRepositories:
    """运营管理后台仓储聚合门面（供 API 服务组合根进行依赖注入装配）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.workspaces = SqlWorkspaceRepository(sessions)
        self.memberships = SqlMembershipRepository(sessions)
        self.knowledge_bases = SqlKnowledgeBaseRepository(sessions)
        self.documents = SqlDocumentRepository(sessions)
        self.chunks = SqlChunkRepository(sessions)
        self.feedback = SqlFeedbackRepository(sessions)
        self.conversations = SqlConversationRepository(sessions)
        self.model_targets = SqlModelTargetRepository(sessions)
        self.outbox = SqlOutboxRepository(sessions)
        self.audit = SqlAuditRepository(sessions)
        self.runs = SqlRunListingRepository(sessions)
        self.mappings = SqlQueryTermMappingRepository(sessions)
        self.credentials = SqlCredentialRepository(sessions)
        self.users = SqlAdminUserRepository(sessions)
        self.sample_questions = SqlSampleQuestionRepository(sessions)
        self.ingestion_runs = SqlIngestionRunListing(sessions)
        self.ingestion = SqlIngestionRunRepository(sessions)
