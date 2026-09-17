"""PostgreSQL 业务数据模型定义（规范数据模型；所有业务实体主键均采用 uuid7）。

定义聊天运行、会话消息、知识库文档与系统配置相关的持久化模型；
ChatRun 为业务事实的唯一真相来源，外部观测追踪系统仅通过关联标识对接，数据库内不冗余存储完整追踪调用树。
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from medicalrag_core.ids import uuid7


def _utcnow() -> datetime:
    """UTC 时间戳，且在同一进程内**严格单调递增**。

    本地时钟粒度可能使连续插入取到同一时刻（Windows 尤其明显），而 uuid7 的低位是随机数，
    所以时间并列时排序会退化为随机 —— 会话消息顺序会错乱（记忆窗口按时间正序读取）。
    这里把时间戳拨到至少比上次大 1 微秒，保证“插入顺序 == 时间顺序”。
    """
    global _last_timestamp
    now = time.time()
    if now <= _last_timestamp:
        now = _last_timestamp + 1e-6
    _last_timestamp = now
    return datetime.fromtimestamp(now, tz=UTC)


_last_timestamp = 0.0


def _iso(value: datetime | None) -> str | None:
    """行时间戳 → ISO 字符串（领域实体的 ``created_at``/``updated_at`` 形态）。"""
    return str(value) if value is not None else None


class Base(DeclarativeBase):
    """声明式基类。

    未引入 naming_convention：库里已有 8 个 revision 创建的约束使用 PG 默认名，
    改成命名规范要求对全部约束写重命名迁移，收益仅是可读性，不做（YAGNI）。
    """

    pass


class User(Base):
    """用户账户实体；email 全局唯一，password_hash 采用 argon2id 加密（严禁在 API 响应中返回）。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChatRun(Base):
    """单次聊天运行记录：维护状态、最终结果、生效策略版本及观测链路追踪关联键。"""

    __tablename__ = "chat_runs"
    # 聊天幂等：同一会话同时至多一条非终态 Run（并发重复提交在数据库层面直接拒绝）
    __table_args__ = (
        Index(
            "uq_chat_runs_running",
            "conversation_id",
            unique=True,
            postgresql_where=text("status NOT IN ('completed', 'cancelled', 'failed')"),
            sqlite_where=text("status NOT IN ('completed', 'cancelled', 'failed')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32))
    # 用户原始问题（运营追踪页展示；回答文本存 assistant_message）
    question: Mapped[str | None] = mapped_column(Text)
    # 命中的证据集合（JSON 数组，Evidence.to_payload 结构；供溯源与反馈质量分析）
    evidence: Mapped[list | None] = mapped_column(JSON)
    assistant_message: Mapped[str | None] = mapped_column(Text)
    retrieval_policy_version: Mapped[int | None] = mapped_column(Integer)
    # 链路追踪关联键：Aegra thread_id（映射至 Phoenix session_id）
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunEvent(Base):
    """聊天运行状态迁移事件实体（用于合规审计：短路拦截原因、安全风险等级与生效策略版本均写入事件流）。"""

    __tablename__ = "run_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_runs.id"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Message(Base):
    """会话消息实体（包含用户提问与助手回答；System 角色用于系统状态播报）。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IntentNodeRow(Base):
    """动态意图树节点配置表（以业务唯一标识码为主键）。

    slot_schema 模式预留后续扩展；示例问题列表以 JSON 数组形式存储。
    """

    __tablename__ = "intent_nodes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str | None] = mapped_column(String(128))
    examples: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    safety_class: Mapped[str] = mapped_column(String(16), default="general")


class IngestionRun(Base):
    """文档摄取运行实体（针对单个 Document 的全流程异步摄取作业；PostgreSQL 为唯一事实来源）。

    ``data`` 字段（映射至 metadata 列）维护作业级上下文元数据（包括 object_key、title、expected_chunks、artifact_ref 等），
    随摄取各阶段的顺利完成逐步递增写入。
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class IngestionRunStage(Base):
    """已完成摄取阶段记录表；UNIQUE(run_id, stage) 唯一约束确保阶段重试幂等执行。"""

    __tablename__ = "ingestion_run_stages"
    __table_args__ = (UniqueConstraint("run_id", "stage", name="uq_ingestion_run_stage"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkspaceRow(Base):
    """工作区实体（成员共享资源的物理隔离边界）。"""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkspaceMemberRow(Base):
    """用户在工作区内的成员资格与权限角色记录（普通成员 member / 操作员 operator）。"""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_workspace_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeBaseRow(Base):
    """知识库实体（用户或团队作用域下的医学资料来源组织单元）。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class DocumentRow(Base):
    """文档实体（提交至知识库的原始医学资料来源；published=False 时其 Chunk 不参与检索，支持可逆下架）。"""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingestion_state: Mapped[str] = mapped_column(String(32), nullable=False, default="accepted")
    # 生命周期管理：published=False 时关联的所有 Chunk 均不可被检索到
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChunkRow(Base):
    """文档分块元数据与正文记录表（向量存储于 Qdrant 集合中）。"""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    headings: Mapped[list] = mapped_column(JSON, default=list)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_ref: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConversationRow(Base):
    """会话实体（用户所有的多轮消息交互历史；thread_id 关联 Aegra 运行时上下文）。"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新会话")
    summary: Mapped[str | None] = mapped_column(Text)
    # 记忆摘要水位：已被摘要覆盖的消息条数（与最近窗口配合做增量压缩）
    summary_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thread_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class FeedbackRow(Base):
    """用户反馈记录表（规范用户故事 18：点赞/点踩反馈供检索调优与模型生成质量审核）。"""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelTargetRow(Base):
    """模型目标配置与熔断器健康状态记录表（规范用户故事 26 / 27）。"""

    __tablename__ = "model_targets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_state: Mapped[str] = mapped_column(String(16), nullable=False, default="closed")
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 熔断开启时间：冷却到期后路由器将其翻转 HALF_OPEN 放行探测请求
    circuit_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OutboxRow(Base):
    """事务性 Outbox 事件表（部分索引 ix_outbox_unprocessed 服务 relay 轮询）。"""

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "ix_outbox_unprocessed",
            "created_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 领取租约：relay 领取时打标，崩溃后租约过期自动重投（at-least-once）
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)


class SampleQuestionRow(Base):
    """推荐样例问题配置表。"""

    __tablename__ = "sample_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    intent_node_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class QueryTermMappingRow(Base):
    """医学专业术语与意图节点映射配置表。"""

    __tablename__ = "query_term_mappings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    term: Mapped[str] = mapped_column(String(128), nullable=False)
    intent_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
