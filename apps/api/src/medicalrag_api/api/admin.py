"""运营管理控制台 API 路由（需 operator 权限授权；对应产品规范用户故事 26-33 的运营数据面）。

各端点精确对应前端运营后台的各个业务管理模块；全部经由 OperatorRepositories 读写 PostgreSQL 关系库。
涵盖管理看板与性能追踪读面、知识库/文档/切片管理、摄取作业运行历史、意图树与术语映射配置、
模型目标与平台凭据管理、用户与工作区管理、操作审计日志、推荐样例问题、以及用户反馈管理。
"""

from __future__ import annotations

import dataclasses
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from medicalrag_core.ingestion.knowledge import KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.outbox import OutboxMessage
from medicalrag_infra.persistence.models import ChatRun, QueryTermMappingRow

from ..deps import OperatorCtx

router = APIRouter(prefix="/api/admin")


def _repos(request: Request):
    return request.app.state.operator


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
    repos = _repos(request)
    targets = await repos.model_targets.list_all()
    return DashboardOut(
        total_chats=await repos.runs.conversation_count(ctx.workspace_id),
        total_questions=await repos.runs.question_count(ctx.workspace_id),
        avg_latency_ms=await repos.runs.avg_latency_ms(ctx.workspace_id),
        published_docs=await repos.runs.published_docs(ctx.workspace_id),
        failed_runs=await repos.runs.failed_runs(ctx.workspace_id),
        active_model_targets=sum(1 for t in targets if t.circuit_allows),
        degraded_model_targets=sum(1 for t in targets if not t.circuit_allows),
    )


# --- 知识库 / 文档 / 切片 ---


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    chunk_count: int
    created_at: str | None = None
    updated_at: str | None = None


class KnowledgeBaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


@router.get("/knowledge-bases")
async def list_knowledge_bases(ctx: OperatorCtx, request: Request) -> list[KnowledgeBaseOut]:
    repos = _repos(request)
    rows = await repos.knowledge_bases.list_for_workspace(ctx.workspace_id)
    counts = await repos.documents.counts_by_kb(ctx.workspace_id)
    return [
        KnowledgeBaseOut(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            document_count=counts.get(kb.id, 0),
            chunk_count=0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb in rows
    ]


@router.post("/knowledge-bases", status_code=201)
async def create_knowledge_base(
    body: KnowledgeBaseIn, ctx: OperatorCtx, request: Request
) -> KnowledgeBaseOut:
    repos = _repos(request)
    kb = await repos.knowledge_bases.create(
        KnowledgeBase(
            id=str(uuid.uuid7()),
            workspace_id=ctx.workspace_id,
            name=body.name,
            description=body.description,
        )
    )
    return KnowledgeBaseOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        document_count=0,
        chunk_count=0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


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


async def _require_document(repos, doc_id: str):
    document = await repos.documents.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document


@router.post("/documents/{doc_id}/unpublish", status_code=202)
async def unpublish_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """下架文档（ADR 0079）：经由 Outbox 清除向量点的检索发布资格，使切片退出检索；操作完全可逆。"""
    _require_uuid(doc_id)
    repos = _repos(request)
    await _require_document(repos, doc_id)
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="document",
            aggregate_id=doc_id,
            event_type="document.unpublish",
            payload={},
        )
    )


@router.post("/documents/{doc_id}/publish", status_code=202)
async def republish_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """重新发布文档（ADR 0079）：恢复文档的检索发布资格（仅适用于历史已完成摄取的文档）。"""
    _require_uuid(doc_id)
    repos = _repos(request)
    document = await _require_document(repos, doc_id)
    if document.ingestion_state is not IngestionRunState.PUBLISHED:
        raise HTTPException(status_code=409, detail="文档尚未完成发布流程")
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="document",
            aggregate_id=doc_id,
            event_type="document.publish",
            payload={},
        )
    )


@router.delete("/documents/{doc_id}", status_code=202)
async def delete_document(doc_id: str, ctx: OperatorCtx, request: Request) -> None:
    """级联物理删除文档（ADR 0079）：经由 Outbox 异步级联清除 Qdrant 向量点及 PostgreSQL 中的切片和文档实体行。

    仅处于终态（PUBLISHED 或 FAILED）的文档允许执行删除：若删除正在进行摄取的文档，后续摄取阶段将向已删除的记录写入状态并产生孤儿切片。
    """
    _require_uuid(doc_id)
    repos = _repos(request)
    document = await _require_document(repos, doc_id)
    if document.ingestion_state not in {IngestionRunState.PUBLISHED, IngestionRunState.FAILED}:
        raise HTTPException(status_code=409, detail="文档摄取未结束，暂不能删除")
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="document",
            aggregate_id=doc_id,
            event_type="document.delete",
            payload={},
        )
    )


@router.post("/maintenance/orphan-scan", status_code=202)
async def trigger_orphan_scan(ctx: OperatorCtx, request: Request) -> None:
    """手动触发孤儿切片对账与清理任务（ADR 0079；供管理员按需触发）。"""
    repos = _repos(request)
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="document",
            aggregate_id=str(uuid.uuid7()),
            event_type="document.scan_orphans",
            payload={},
        )
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
    """获取文档原始文件二进制流（供在线预览或下载；遵循 ADR 0068 格式化渲染规范）。"""
    from fastapi.responses import Response

    from medicalrag_core.storage.ports import ObjectRef

    _require_uuid(doc_id)
    repos = _repos(request)
    document = await repos.documents.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    object_key = await repos.ingestion_runs.object_key_for_document(doc_id)
    if not object_key:
        raise HTTPException(status_code=404, detail="文档尚未完成摄取，暂无可预览内容")
    content = await request.app.state.object_storage.get(
        ObjectRef(workspace_id=document.workspace_id, key=object_key)
    )
    content_type = _content_type_for(document.format)
    return Response(content=content, media_type=content_type)


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
    repos = _repos(request)
    rows = await repos.ingestion_runs.list_for_workspace(ctx.workspace_id)
    return [IngestionRunOut(**row) for row in rows]  # type: ignore[arg-type]


@router.post("/ingestion-runs/{run_id}/retry")
async def retry_ingestion_run(run_id: str, ctx: OperatorCtx, request: Request) -> dict[str, str]:
    repos = _repos(request)
    runs = await repos.ingestion_runs.list_for_workspace(ctx.workspace_id)
    run = next((r for r in runs if r["id"] == run_id), None)
    if run is None or run["status"] != IngestionRunState.FAILED.value:
        raise HTTPException(status_code=409, detail="仅 FAILED 运行可重试")
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="ingestion_run",
            aggregate_id=run_id,
            event_type="ingestion.stage",
            payload={"stage": IngestionRunState.ACCEPTED.value},
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
    name: str | None = None
    description: str | None = None
    examples: list[str] | None = None
    enabled: bool | None = None
    safety_scope: str | None = None
    parent_id: str | None = None
    kind: str | None = None


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
    enabled: bool
    created_at: str | None = None


def _mapping_out(row: QueryTermMappingRow) -> MappingOut:
    return MappingOut(
        id=str(row.id),
        term=row.term,
        intent_node_id=row.intent_node_id,
        enabled=row.enabled,
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
    await _repos(request).mappings.add(body.term, body.intent_node_id)
    return {"status": "ok"}


# --- 模型目标 / 凭据 / 设置 ---


class ModelTargetOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    capabilities: list[str]
    priority: int
    status: str
    circuit_state: str


class ModelTargetPatch(BaseModel):
    priority: int | None = None


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


@router.patch("/model-targets/{target_id}")
async def update_model_target(
    target_id: str, body: ModelTargetPatch, _: OperatorCtx, request: Request
) -> dict[str, str]:
    repos = _repos(request)
    targets = await repos.model_targets.list_all()
    target = next((t for t in targets if t.id == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="模型目标不存在")
    await repos.model_targets.save(
        dataclasses.replace(
            target, priority=body.priority if body.priority is not None else target.priority
        )
    )
    return {"status": "ok"}


class CredentialOut(BaseModel):
    id: str
    provider_name: str
    bound_target_id: str | None
    last_tested_at: str | None
    last_test_result: str | None


@router.get("/credentials")
async def list_credentials(_: OperatorCtx, request: Request) -> list[CredentialOut]:
    rows = await _repos(request).credentials.list_all()
    return [
        CredentialOut(
            id=str(row.id),
            provider_name=row.provider_name,
            bound_target_id=str(row.bound_target_id) if row.bound_target_id else None,
            last_tested_at=str(row.last_tested_at) if row.last_tested_at else None,
            last_test_result=row.last_test_result,
        )
        for row in rows
    ]


# --- 追踪 ---


class TraceOut(BaseModel):
    id: str
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
        id=str(run.id),
        run_id=str(run.id)[:12],
        conversation_id=str(run.conversation_id),
        question=run.assistant_message or "",
        outcome=run.outcome or run.status,
        latency_ms=latency,
        trace_id=run.trace_id,
        created_at=str(run.created_at) if run.created_at else None,
    )


@router.get("/traces")
async def list_traces(ctx: OperatorCtx, request: Request) -> list[TraceOut]:
    runs = await _repos(request).runs.recent_runs(ctx.workspace_id, limit=100)
    return [_trace_out(run) for run in runs]


@router.get("/traces/{run_id}")
async def get_trace(run_id: str, ctx: OperatorCtx, request: Request) -> TraceOut:
    repos = _repos(request)
    runs = await repos.runs.recent_runs(ctx.workspace_id, limit=1000)
    run = next((r for r in runs if str(r.id) == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail="追踪记录不存在")
    return _trace_out(run)


# --- 用户 ---


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    workspace_name: str
    status: str
    created_at: str | None


@router.get("/users")
async def list_users(_: OperatorCtx, request: Request) -> list[UserOut]:
    rows = await _repos(request).users.list_for_admin()
    return [
        UserOut(
            id=row["id"],
            email=row["email"],
            role="admin",
            workspace_name="",
            status=row["status"],
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


# --- 审计 / 样例问题 / 反馈 ---


class AuditOut(BaseModel):
    id: str
    actor_email: str
    action: str
    entity_type: str
    entity_name: str
    detail: str
    created_at: str | None


@router.get("/audit")
async def list_audit(ctx: OperatorCtx, request: Request) -> list[AuditOut]:
    events = await _repos(request).audit.list_for_workspace(ctx.workspace_id)
    return [
        AuditOut(
            id=e.id,
            actor_email=e.actor_email,
            action=e.action,
            entity_type=e.entity_type,
            entity_name=e.entity_name,
            detail=e.detail,
            created_at=e.created_at,
        )
        for e in events
    ]


class SampleQuestionOut(BaseModel):
    id: str
    text: str
    intent_node_id: str | None
    enabled: bool
    created_at: str | None


@router.get("/sample-questions")
async def list_sample_questions(ctx: OperatorCtx, request: Request) -> list[SampleQuestionOut]:
    rows = await _repos(request).sample_questions.list_for_workspace(ctx.workspace_id)
    return [SampleQuestionOut(**row) for row in rows]  # type: ignore[arg-type]


class FeedbackOut(BaseModel):
    id: str
    message_id: str
    conversation_id: str
    value: str
    comment: str | None
    created_at: str | None


@router.get("/feedback")
async def list_feedback(ctx: OperatorCtx, request: Request) -> list[FeedbackOut]:
    items = await _repos(request).feedback.list_for_workspace(ctx.workspace_id)
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
