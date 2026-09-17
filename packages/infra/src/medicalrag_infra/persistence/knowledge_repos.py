"""知识库 / 文档 / 分块 / 摄取列表持久化仓储（自 operator.py 按领域聚合拆分；组合门面见 operator.py）。"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document, KnowledgeBase
from medicalrag_core.ingestion.state_machine import IngestionRunState

from .models import (
    ChunkRow,
    DocumentRow,
    IngestionRun,
    IngestionRunStage,
    KnowledgeBaseRow,
    _iso,
)


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
        """删除指定的文档实体及其关联分块、摄取运行与阶段记录（Qdrant 向量点由 Worker 异步优先级联清理）。

        IngestionRunStage 的外键无 ON DELETE CASCADE，必须显式先行删除——
        遗漏该步会让任何完成过阶段的文档在 PG 上删除必失败（SQLite 默认不强制外键，测试侧以 pragma 防回归）。
        """
        doc_id = uuid.UUID(document_id)
        async with self._sessions() as session:
            await session.execute(delete(ChunkRow).where(ChunkRow.document_id == doc_id))
            await session.execute(
                delete(IngestionRunStage).where(
                    IngestionRunStage.run_id.in_(
                        select(IngestionRun.id).where(IngestionRun.document_id == doc_id)
                    )
                )
            )
            await session.execute(delete(IngestionRun).where(IngestionRun.document_id == doc_id))
            await session.execute(delete(DocumentRow).where(DocumentRow.id == doc_id))
            await session.commit()

    async def set_chunk_count(self, document_id: str, count: int) -> None:
        """回写文档分块总数（发布阶段调用，供管理后台列表展示）。"""
        async with self._sessions() as session:
            row = await session.get(DocumentRow, uuid.UUID(document_id))
            if row is None:
                raise KeyError(f"document 不存在: {document_id}")
            row.chunk_count = count
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
    """文档分块持久化仓储：实现 ChunkRepository 协议端口。"""

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

    async def delete_for_document(self, document_id: str) -> None:
        """删除指定文档的全部分块记录（重新摄取前执行先删后建）。"""
        async with self._sessions() as session:
            await session.execute(
                delete(ChunkRow).where(ChunkRow.document_id == uuid.UUID(document_id))
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


class SqlIngestionRunListing:
    """文档摄取运行管理读面仓储：支持按工作区查询摄取作业执行历史（包含关联文档标题及各阶段状态）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def object_key_for_document(self, document_id: str) -> str | None:
        """获取指定文档最新一次摄取运行的对象存储 Key（供文件预览与下载使用）。"""
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

    async def get_run(self, run_id: str) -> dict[str, object] | None:
        """按主键获取单条摄取运行记录（重放前校验 FAILED 状态与失败阶段；全平台语义）。"""
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return None
        async with self._sessions() as session:
            run = await session.get(IngestionRun, run_uuid)
            if run is None:
                return None
            data = run.data or {}
            return {
                "id": str(run.id),
                "status": run.state,
                "failed_stage": str(data.get("failed_stage", "")) or None,
            }

    async def list_all(self) -> tuple[dict[str, object], ...]:
        """全平台摄取运行历史（operator 数据面语义）。"""
        async with self._sessions() as session:
            query = select(IngestionRun).order_by(IngestionRun.created_at.desc())
            runs = (await session.scalars(query)).all()
            if not runs:
                return ()
            # 批量预取关联文档与阶段行（各一条 IN 查询），消除逐 Run 的 N+1 循环查询
            documents = {
                doc.id: doc
                for doc in (
                    await session.scalars(
                        select(DocumentRow).where(
                            DocumentRow.id.in_({run.document_id for run in runs})
                        )
                    )
                ).all()
            }
            stage_rows = (
                await session.scalars(
                    select(IngestionRunStage)
                    .where(IngestionRunStage.run_id.in_([run.id for run in runs]))
                    .order_by(IngestionRunStage.created_at)
                )
            ).all()
            stages_by_run: dict[object, list[IngestionRunStage]] = {}
            for stage_row in stage_rows:
                stages_by_run.setdefault(stage_row.run_id, []).append(stage_row)
            out: list[dict[str, object]] = []
            for run in runs:
                document = documents.get(run.document_id)
                data = run.data or {}
                failed_stage = str(data.get("failed_stage", ""))
                out.append(
                    {
                        "id": str(run.id),
                        "document_title": document.title if document else str(run.document_id),
                        "status": run.state,
                        "failure_reason": str(data.get("failure_reason", "")) or None,
                        "failed_stage": failed_stage or None,
                        "stages": [
                            {
                                "name": s.stage,
                                "label": s.stage,
                                "status": "failed" if s.stage == failed_stage else "succeeded",
                            }
                            for s in stages_by_run.get(run.id, [])
                        ],
                        "started_at": str(run.created_at) if run.created_at else None,
                    }
                )
            return tuple(out)
