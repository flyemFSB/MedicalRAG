"""SqlChunkRepository 跨层契约测试：worker 生成的分块记录必须能被关系仓储直接落库。

回归背景：worker 曾以 "document_id:index" 字符串作为 chunk id，而仓储强制 UUID 解析，
两层各自的测试均未暴露该缝隙（worker 用内存 fake、仓储测试喂合法 UUID），真实链路 chunking 必崩。
本测试固定该接缝的契约：chunk id 由 worker 侧按 uuid7 生成。
"""

import uuid

import pytest

from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.knowledge_repos import SqlChunkRepository
from medicalrag_infra.persistence.models import Base


@pytest.fixture
async def repo(persistence_url: str) -> SqlChunkRepository:
    engine, factory = create_engine_and_session_factory(persistence_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield SqlChunkRepository(factory)
    await engine.dispose()


def _record(workspace_id: str, document_id: str, index: int) -> ChunkRecord:
    return ChunkRecord(
        id=str(uuid7()),
        document_id=document_id,
        workspace_id=workspace_id,
        text=f"分块正文 {index}",
        headings=("第一章", "第一节"),
        index=index,
        checksum=f"{index:064d}",
        token_count=8,
    )


async def test_worker_style_chunk_record_roundtrips(repo: SqlChunkRepository):
    """worker 产出的 ChunkRecord（uuid7 主键）可直接落库并按序读回。"""
    workspace_id, document_id = str(uuid7()), str(uuid7())
    records = tuple(_record(workspace_id, document_id, i) for i in range(3))
    await repo.insert_many(records)
    loaded = await repo.list_for_document(document_id)
    assert [c.index for c in loaded] == [0, 1, 2]
    assert all(uuid.UUID(c.id).version == 7 for c in loaded)
    assert loaded[0].headings == ("第一章", "第一节")


async def test_delete_for_document_clears_chunks(repo: SqlChunkRepository):
    """重摄先删后建契约：delete_for_document 清空该文档分块且不影响其他文档。"""
    workspace_id, doc_a, doc_b = str(uuid7()), str(uuid7()), str(uuid7())
    await repo.insert_many(
        (
            _record(workspace_id, doc_a, 0),
            _record(workspace_id, doc_a, 1),
            _record(workspace_id, doc_b, 0),
        )
    )
    await repo.delete_for_document(doc_a)
    assert await repo.count_for_document(doc_a) == 0
    assert await repo.count_for_document(doc_b) == 1


async def test_non_uuid_chunk_id_is_rejected(repo: SqlChunkRepository):
    """契约护栏：非 UUID 的 chunk id（如历史 "doc:index" 形式）在仓储边界即报错，不得静默入库。"""
    workspace_id, document_id = str(uuid7()), str(uuid7())
    bad = ChunkRecord(
        id=f"{document_id}:0",
        document_id=document_id,
        workspace_id=workspace_id,
        text="x",
        headings=(),
        index=0,
        checksum="0" * 64,
    )
    with pytest.raises(ValueError):
        await repo.insert_many((bad,))
