"""运营管理控制台 API 路由（需 operator 权限授权；对应产品规范用户故事 26-33 的运营数据面）。

各端点精确对应前端运营后台的各个业务管理模块；全部经由 OperatorRepositories 读写 PostgreSQL 关系库。
涵盖管理看板与性能追踪读面、知识库/文档/分块管理、摄取作业运行历史、意图树与术语映射配置、
模型目标管理、用户与工作区管理、以及用户反馈管理。

权限语义（刻意设计）：operator 是**平台级**角色（OPERATOR_EMAILS 白名单授予，见 deps.require_operator），
因此本模块的读/写按设计跨工作区；按 workspace_id 再过滤会让运营台看不到全平台数据。
与之相对，面向普通用户的对象级写路径必须校验归属（见 feedback.submit_feedback）。
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.knowledge import Document, KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.records import OutboxMessage
from medicalrag_infra.persistence.models import ChatRun, QueryTermMappingRow
from medicalrag_infra.persistence.operator import OperatorRepositories

from ..deps import OperatorCtx

router = APIRouter(prefix="/api/admin")


def _repos(request: Request) -> OperatorRepositories:
    return request.app.state.operator


async def _append_outbox(
    repos: OperatorRepositories, *, aggregate_type: str, aggregate_id: str, event_type: str
) -> None:
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid7()),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload={},
        )
    )


def _require_uuid(raw: str) -> uuid.UUID:
    """校验路径参数必须为合法的 uuid7 格式；格式非法抛出 404 异常（系统信任边界入参门禁校验，开发规范 §1.3）。"""
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail="无效的资源标识") from None


# --- 运营管理看板 ---


class DashboardOut(BaseModel):
    total_chats: int
    total_questions: int
    avg_latency_ms: float
    published_docs: int
    failed_runs: int
    active_model_targets: int
    degraded_model_targets: int


@router.get("/dashboard")
async def dashboard(ctx: OperatorCtx, request: Request) -> DashboardOut:
    """运营看板：operator 为平台级角色，统计口径为全平台（不按当前个人工作区过滤）。"""
    repos = _repos(request)
    targets = await repos.model_targets.list_all()
    return DashboardOut(
        total_chats=await repos.runs.conversation_count(),
        total_questions=await repos.runs.question_count(),
        avg_latency_ms=await repos.runs.avg_latency_ms(),
        published_docs=await repos.runs.published_docs(),
        failed_runs=await repos.runs.failed_runs(),
        active_model_targets=sum(1 for t in targets if t.circuit_allows),
        degraded_model_targets=sum(1 for t in targets if not t.circuit_allows),
    )


# --- 知识库 / 文档 / 分块 ---


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: str | None = None
    updated_at: str | None = None


class KnowledgeBaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


def _kb_out(kb: KnowledgeBase, *, document_count: int = 0) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        document_count=document_count,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.get("/knowledge-bases")
async def list_knowledge_bases(ctx: OperatorCtx, request: Request) -> list[KnowledgeBaseOut]:
    repos = _repos(request)
    rows = await repos.knowledge_bases.list_for_workspace(ctx.workspace_id)
    counts = await repos.documents.counts_by_kb(ctx.workspace_id)
    return [_kb_out(kb, document_count=counts.get(kb.id, 0)) for kb in rows]


@router.post("/knowledge-bases", status_code=201)
async def create_knowledge_base(
    body: KnowledgeBaseIn, ctx: OperatorCtx, request: Request
) -> KnowledgeBaseOut:
    repos = _repos(request)
    kb = await repos.knowledge_bases.create(
        KnowledgeBase(
            id=str(uuid7()),
            workspace_id=ctx.workspace_id,
            name=body.name,
            description=body.description,
        )
    )
    return _kb_out(kb)


class DocumentOut(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    format: str
    ingestion_status: str
    published: bool
    chunk_count: int
    size_bytes: int
    created_at: str | None = None


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(kb_id: str, _: OperatorCtx, request: Request) -> list[DocumentOut]:
    _require_uuid(kb_id)
    repos = _repos(request)
    rows = await repos.documents.list_for_knowledge_base(kb_id)
    return [
        DocumentOut(
            id=d.id,
            knowledge_base_id=d.knowledge_base_id,
            title=d.title,
            format=d.format,
            ingestion_status=d.ingestion_state.value,
            published=d.published,
            chunk_count=d.chunk_count,
            size_bytes=d.size_bytes,
            created_at=d.created_at,
        )
        for d in rows
    ]


async def _require_document(repos: OperatorRepositories, doc_id: str) -> Document:
    document = await repos.documents.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document


@router.post("/documents/{doc_id}/unpublish", status_code=202)
async def unpublish_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """下架文档：经由 Outbox 清除向量点的检索发布资格，使分块退出检索；操作完全可逆。"""
    _require_uuid(doc_id)
    repos = _repos(request)
    await _require_document(repos, doc_id)
    await _append_outbox(
        repos, aggregate_type="document", aggregate_id=doc_id, event_type="document.unpublish"
    )


@router.post("/documents/{doc_id}/publish", status_code=202)
async def republish_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """重新发布文档：恢复文档的检索发布资格（仅适用于历史已完成摄取的文档）。"""
    _require_uuid(doc_id)
    repos = _repos(request)
    document = await _require_document(repos, doc_id)
    if document.ingestion_state is not IngestionRunState.PUBLISHED:
        raise HTTPException(status_code=409, detail="文档尚未完成发布流程")
    await _append_outbox(
        repos, aggregate_type="document", aggregate_id=doc_id, event_type="document.publish"
    )


@router.delete("/documents/{doc_id}", status_code=202)
async def delete_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """级联物理删除文档：经由 Outbox 异步级联清除 Qdrant 向量点及 PostgreSQL 中的分块和文档实体行。

    仅处于终态（PUBLISHED 或 FAILED）的文档允许执行删除：若删除正在进行摄取的文档，后续摄取阶段将向已删除的记录写入状态并产生孤儿分块。
    """
    _require_uuid(doc_id)
    repos = _repos(request)
    document = await _require_document(repos, doc_id)
    if document.ingestion_state not in {IngestionRunState.PUBLISHED, IngestionRunState.FAILED}:
        raise HTTPException(status_code=409, detail="文档摄取未结束，暂不能删除")
    await _append_outbox(
        repos, aggregate_type="document", aggregate_id=doc_id, event_type="document.delete"
    )


@router.post("/maintenance/orphan-scan", status_code=202)
async def trigger_orphan_scan(ctx: OperatorCtx, request: Request) -> None:
    """手动触发孤儿分块对账与清理任务（供运营管理员按需触发）。"""
    await _append_outbox(
        _repos(request),
        aggregate_type="document",
        aggregate_id=str(uuid7()),
        event_type="document.scan_orphans",
    )


@router.post("/maintenance/object-scan", status_code=202)
async def trigger_object_scan(ctx: OperatorCtx, request: Request) -> None:
    """手动触发对象存储孤儿对象对账与清理任务（清理未被任何摄取运行元数据引用的存储对象）。"""
    await _append_outbox(
        _repos(request),
        aggregate_type="document",
        aggregate_id=str(uuid7()),
        event_type="objects.scan_orphans",
    )


class ChunkOut(BaseModel):
    id: str
    document_id: str
    content: str
    page_ref: str | None
    headings: list[str]
    token_count: int
    created_at: str | None = None


@router.get("/documents/{doc_id}/chunks")
async def list_chunks(doc_id: str, _: OperatorCtx, request: Request) -> list[ChunkOut]:
    _require_uuid(doc_id)
    repos = _repos(request)
    rows = await repos.chunks.list_for_document(doc_id)
    return [
        ChunkOut(
            id=c.id,
            document_id=c.document_id,
            content=c.text,
            page_ref=c.page_ref,
            headings=list(c.headings),
            token_count=c.token_count,
            created_at=c.created_at,
        )
        for c in rows
    ]


@router.get("/documents/{doc_id}/content")
async def get_document_content(doc_id: str, _: OperatorCtx, request: Request):
    """获取文档原始文件二进制流（供在线预览或下载，遵循格式化渲染规范）。

    流式产出（分块读取对象存储），不把最大 200MB 的原始对象整读进进程内存——
    两个并发预览即可击穿容器内存上限。
    """
    from fastapi.responses import StreamingResponse

    from medicalrag_core.storage.ports import ObjectRef

    _require_uuid(doc_id)
    repos = _repos(request)
    document = await _require_document(repos, doc_id)
    object_key = await repos.ingestion_runs.object_key_for_document(doc_id)
    if not object_key:
        raise HTTPException(status_code=404, detail="文档尚未完成摄取，暂无可预览内容")
    content_type = _content_type_for(document.format)
    return StreamingResponse(
        request.app.state.object_storage.get_stream(
            ObjectRef(workspace_id=document.workspace_id, key=object_key)
        ),
        media_type=content_type,
    )


def _content_type_for(format_: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".md": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(format_, "application/octet-stream")


# --- 摄取运行 ---


class IngestionRunOut(BaseModel):
    id: str
    document_title: str
    status: str
    stages: list[dict[str, str]]
    started_at: str | None = None


@router.get("/ingestion-runs")
async def list_ingestion_runs(ctx: OperatorCtx, request: Request) -> list[IngestionRunOut]:
    """摄取运行历史（平台级全量；operator 数据面语义见模块 docstring）。"""
    repos = _repos(request)
    rows = await repos.ingestion_runs.list_all()
    return [IngestionRunOut(**row) for row in rows]  # type: ignore[arg-type]


@router.post("/ingestion-runs/{run_id}/retry")
async def retry_ingestion_run(run_id: str, ctx: OperatorCtx, request: Request) -> dict[str, str]:
    """重放失败的摄取运行：从记录的失败阶段复位续跑（而非从头重摄）。"""
    _require_uuid(run_id)
    repos = _repos(request)
    run = await repos.ingestion_runs.get_run(run_id)
    if run is None or run["status"] != IngestionRunState.FAILED.value:
        raise HTTPException(status_code=409, detail="仅 FAILED 运行可重试")
    stage = run.get("failed_stage") or IngestionRunState.ACCEPTED.value
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid7()),
            aggregate_type="ingestion_run",
            aggregate_id=run_id,
            event_type="ingestion.stage",
            payload={"stage": stage},
        )
    )
    return {"status": "ok"}


# --- 意图树 / 映射 ---


class IntentNodeOut(BaseModel):
    id: str
    name: str
    description: str
    parent_id: str | None
    level: str
    kind: str
    enabled: bool
    examples: list[str]
    safety_scope: str | None


@router.get("/intent-tree")
async def list_intent_tree(_: OperatorCtx, request: Request) -> list[IntentNodeOut]:
    nodes = await request.app.state.intent_tree_repo.list_nodes()
    return [
        IntentNodeOut(
            id=n.id,
            name=n.name,
            description=n.description,
            parent_id=n.parent_id,
            level=n.level.value,
            kind=n.kind.value,
            enabled=n.enabled,
            examples=list(n.examples),
            safety_scope=None if n.safety_class.value == "general" else n.safety_class.value,
        )
        for n in nodes
    ]


class IntentNodePatch(BaseModel):
    """意图节点部分更新；枚举字段由 pydantic 在边界校验（非法值 422 而非 500）。"""

    name: str | None = None
    description: str | None = None
    examples: list[str] | None = None
    enabled: bool | None = None
    safety_scope: Literal["treatment", "urgent", "prohibited"] | None = None
    parent_id: str | None = None
    kind: Literal["knowledge", "system"] | None = None


@router.patch("/intent-tree/{node_id}")
async def update_intent_node(
    node_id: str, body: IntentNodePatch, _: OperatorCtx, request: Request
) -> dict[str, str]:
    repo = request.app.state.intent_tree_repo
    nodes = await repo.list_nodes()
    node = next((n for n in nodes if n.id == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    from medicalrag_core.intent.node import IntentKind
    from medicalrag_core.safety.policy import RiskClass

    updated = dataclasses.replace(
        node,
        name=body.name if body.name is not None else node.name,
        description=body.description if body.description is not None else node.description,
        examples=tuple(body.examples) if body.examples is not None else node.examples,
        enabled=body.enabled if body.enabled is not None else node.enabled,
        safety_class=RiskClass(body.safety_scope) if body.safety_scope else node.safety_class,
        parent_id=body.parent_id if body.parent_id is not None else node.parent_id,
        kind=IntentKind(body.kind) if body.kind else node.kind,
    )
    await repo.update_node(updated)
    return {"status": "ok"}


class MappingOut(BaseModel):
    id: str
    term: str
    intent_node_id: str
    created_at: str | None = None


def _mapping_out(row: QueryTermMappingRow) -> MappingOut:
    return MappingOut(
        id=str(row.id),
        term=row.term,
        intent_node_id=row.intent_node_id,
        created_at=str(row.created_at) if row.created_at else None,
    )


@router.get("/query-term-mappings")
async def list_mappings(_: OperatorCtx, request: Request) -> list[MappingOut]:
    return [_mapping_out(row) for row in await _repos(request).mappings.list_all()]


class MappingIn(BaseModel):
    term: str = Field(min_length=1)
    intent_node_id: str


@router.post("/query-term-mappings", status_code=201)
async def create_mapping(body: MappingIn, _: OperatorCtx, request: Request) -> dict[str, str]:
    # 边界校验：意图节点必须真实存在，脏映射静默入库会误导检索路由
    nodes = await request.app.state.intent_tree_repo.list_nodes()
    if body.intent_node_id not in {n.id for n in nodes}:
        raise HTTPException(status_code=422, detail="意图节点不存在")
    await _repos(request).mappings.add(body.term, body.intent_node_id)
    return {"status": "ok"}


# --- 模型目标 / 设置 ---


class ModelTargetOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    capabilities: list[str]
    priority: int
    status: str
    circuit_state: str


@router.get("/model-targets")
async def list_model_targets(_: OperatorCtx, request: Request) -> list[ModelTargetOut]:
    targets = await _repos(request).model_targets.list_all()
    return [
        ModelTargetOut(
            id=t.id,
            name=t.name,
            provider=t.provider,
            model=t.model,
            capabilities=sorted(t.capabilities),
            priority=t.priority,
            status="healthy" if t.circuit_allows else "degraded",
            circuit_state=t.circuit.value,
        )
        for t in targets
    ]


# --- 追踪 ---


class TraceOut(BaseModel):
    run_id: str
    conversation_id: str
    question: str
    outcome: str
    latency_ms: int
    trace_id: str | None
    created_at: str | None


def _trace_out(run: ChatRun) -> TraceOut:
    latency = (
        int((run.completed_at - run.created_at).total_seconds() * 1000)
        if run.completed_at is not None and run.created_at is not None
        else 0
    )
    return TraceOut(
        run_id=str(run.id),
        conversation_id=str(run.conversation_id),
        question=run.question or "",
        outcome=run.outcome or run.status,
        latency_ms=latency,
        trace_id=run.trace_id,
        created_at=str(run.created_at) if run.created_at else None,
    )


@router.get("/traces")
async def list_traces(ctx: OperatorCtx, request: Request) -> list[TraceOut]:
    """追踪列表（平台级全量；operator 数据面语义见模块 docstring）。"""
    runs = await _repos(request).runs.recent_runs(limit=100)
    return [_trace_out(run) for run in runs]


@router.get("/traces/{run_id}")
async def get_trace(run_id: str, ctx: OperatorCtx, request: Request) -> TraceOut:
    """追踪详情：按主键直查（历史记录可达，且不拖全量列表线性查找）。"""
    _require_uuid(run_id)
    run = await _repos(request).runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="追踪记录不存在")
    return _trace_out(run)


# --- 用户 ---


class UserOut(BaseModel):
    id: str
    email: str
    created_at: str | None


@router.get("/users")
async def list_users(_: OperatorCtx, request: Request) -> list[UserOut]:
    rows = await _repos(request).users.list_for_admin()
    return [
        UserOut(
            id=row["id"],
            email=row["email"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


class WorkspaceOut(BaseModel):
    id: str
    name: str
    member_count: int
    created_at: str | None


@router.get("/workspaces")
async def list_workspaces(_: OperatorCtx, request: Request) -> list[WorkspaceOut]:
    rows = await _repos(request).workspaces.list_all_with_members()
    return [
        WorkspaceOut(id=ws.id, name=ws.name, member_count=count, created_at=ws.created_at)
        for ws, count in rows
    ]


# --- 反馈 ---


class FeedbackOut(BaseModel):
    id: str
    message_id: str
    conversation_id: str
    value: str
    comment: str | None
    created_at: str | None


@router.get("/feedback")
async def list_feedback(ctx: OperatorCtx, request: Request) -> list[FeedbackOut]:
    """用户反馈（平台级全量；operator 数据面语义见模块 docstring）。"""
    items = await _repos(request).feedback.list_all()
    return [
        FeedbackOut(
            id=f.id,
            message_id=f.message_id,
            conversation_id=f.conversation_id,
            value=f.value.value,
            comment=f.comment,
            created_at=f.created_at,
        )
        for f in items
    ]
