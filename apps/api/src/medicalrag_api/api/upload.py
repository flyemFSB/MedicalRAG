"""文档上传与摄取作业触发 API 路由（遵循异步摄取设计；受支持格式白名单）。

上传流程：
1. 文件数据保存至对象存储（v1 默认使用本地文件系统适配器）；
2. 在数据库中创建 Document 与 IngestionRun 记录（run 元数据携带 object_key、title 与 source_url）；
3. 向事务性 Outbox 写入事件，由后台 Worker 异步领取并推进 9 阶段摄取流水线（ACCEPTED → EXTRACTING）。
多模态及复杂版面文档由 Worker 自动分发至 MinerU 解析。
"""

from __future__ import annotations

import tempfile

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.knowledge import (
    Document,
    UnsupportedSourceFormatError,
    validate_source_format,
)
from medicalrag_core.ingestion.state_machine import IngestionRunState

from ..deps import UserCtx

router = APIRouter(prefix="/api/upload")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 单文件上传大小上限：200MB

# 二进制格式的魔数前缀（借鉴参考实现 ParserRegistry 的字节级事实观：扩展名是展示，字节才是事实）
_MAGIC_BY_FORMAT = {
    ".pdf": b"%PDF",
    ".png": b"\x89PNG",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".docx": b"PK\x03\x04",  # OOXML 系（docx/pptx/xlsx）均为 ZIP 容器
    ".pptx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
}


def _sniff_format_mismatch(ext: str, head: bytes) -> bool:
    """字节级嗅探：声称的二进制格式必须匹配魔数（防扩展名伪装）；文本格式不校验。"""
    magic = _MAGIC_BY_FORMAT.get(ext)
    return magic is not None and not head.startswith(magic)


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

    # 先查大小再读：Starlette 在解析 multipart 时已填好 size，避免把 200MB 先读进内存才拒绝
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 200MB 上限")

    repos = request.app.state.operator
    # 归属校验先于落盘：非法/越权的 knowledge_base_id 必须返回 404，而不是 500 或写出孤儿对象
    knowledge_base = await repos.knowledge_bases.get(knowledge_base_id)
    if knowledge_base is None or knowledge_base.workspace_id != ctx.workspace_id:
        raise HTTPException(status_code=404, detail="知识库不存在")

    document_id = str(uuid7())
    title = file.filename or f"document{ext}"
    storage = request.app.state.object_storage
    # 流式落盘：分块写入临时文件再转存对象存储，200MB 文件不整份载入内存（容器内存 512M 防护）
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as spool:
        while chunk := await file.read(1024 * 1024):
            spool.write(chunk)
        size_bytes = spool.tell()
        spool.seek(0)
        if _sniff_format_mismatch(ext, spool.read(8)):
            raise HTTPException(status_code=415, detail="文件内容与声称的格式不符")
        spool.seek(0)
        ref = await storage.put_file(
            ctx.workspace_id,
            spool,
            content_type=file.content_type or "application/octet-stream",
        )
    # 事务性 Outbox：文档、摄取 Run（含元数据）与事件在同一事务写入，Worker Relay 异步领取
    run_id = await repos.ingestion.enqueue_upload(
        Document(
            id=document_id,
            knowledge_base_id=knowledge_base_id,
            workspace_id=ctx.workspace_id,
            title=title,
            format=ext,
            size_bytes=size_bytes,
            ingestion_state=IngestionRunState.ACCEPTED,
        ),
        {
            "object_key": ref.key,
            "title": title,
            "workspace_id": ctx.workspace_id,
            "document_id": document_id,
        },
        event_type="ingestion.stage",
        payload={"stage": IngestionRunState.ACCEPTED.value},
    )
    return UploadOut(document_id=document_id, run_id=run_id, title=title)
