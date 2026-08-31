"""文档上传与摄取作业触发 API 路由（遵循 ADR 0013 异步摄取设计；ADR 0030 受支持格式白名单）。

上传流程：
1. 文件数据保存至对象存储（v1 默认使用本地文件系统适配器）；
2. 在数据库中创建 Document 与 IngestionRun 记录（run 元数据携带 object_key、title 与 source_url）；
3. 向事务性 Outbox 写入事件，由后台 Worker 异步领取并推进 9 阶段摄取流水线（ACCEPTED → EXTRACTING）。
多模态及复杂版面文档由 Worker 自动分发至 MinerU 解析。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from medicalrag_core.ingestion.knowledge import (
    Document,
    UnsupportedSourceFormatError,
    validate_source_format,
)
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_core.outbox import OutboxMessage

from ..deps import UserCtx

router = APIRouter(prefix="/api/upload")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 单文件上传大小上限：200MB


class UploadOut(BaseModel):
    document_id: str
    run_id: str
    title: str


@router.post("", status_code=201)
async def upload_document(
    ctx: UserCtx,
    request: Request,
    knowledge_base_id: str,
    file: UploadFile,
) -> UploadOut:
    """上传医学文档并初始化异步摄取流水线。"""
    try:
        ext = validate_source_format(file.filename or "")
    except UnsupportedSourceFormatError as exc:
        raise HTTPException(status_code=415, detail=f"不支持的来源格式: {exc}") from exc

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 200MB 上限")

    repos = request.app.state.operator
    document_id = str(uuid.uuid7())
    title = file.filename or f"document{ext}"
    ref = await request.app.state.object_storage.put(
        ctx.workspace_id, data, content_type=file.content_type or "application/octet-stream"
    )
    await repos.documents.create(
        Document(
            id=document_id,
            knowledge_base_id=knowledge_base_id,
            workspace_id=ctx.workspace_id,
            title=title,
            format=ext,
            size_bytes=len(data),
            ingestion_state=IngestionRunState.ACCEPTED,
        )
    )
    run_id = await repos.ingestion.create_run(document_id, ctx.workspace_id)
    await repos.ingestion.set_metadata(run_id, "object_key", ref.key)
    await repos.ingestion.set_metadata(run_id, "title", title)
    await repos.ingestion.set_metadata(run_id, "workspace_id", ctx.workspace_id)
    await repos.ingestion.set_metadata(run_id, "document_id", document_id)

    # ADR 0063 事务性 Outbox：与业务状态同事务写入数据库，Worker Relay 异步领取并调度执行
    await repos.outbox.append(
        OutboxMessage(
            id=str(uuid.uuid7()),
            aggregate_type="ingestion_run",
            aggregate_id=run_id,
            event_type="ingestion.stage",
            payload={"stage": IngestionRunState.ACCEPTED.value},
        )
    )
    return UploadOut(document_id=document_id, run_id=run_id, title=title)
