"""TaskIQ Worker 组合根与 9 阶段摄取流水线行为测试（覆盖 Markdown/TXT 原生解析全流程）。"""

import pytest

from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document
from medicalrag_core.ingestion.state_machine import IngestionRunState, is_terminal
from medicalrag_worker.ingestion import ExtractionError, IngestionDeps, IngestionService
from medicalrag_worker.worker import advance_run, broker, run_ingestion_stage

_STAGES = [
    IngestionRunState.ACCEPTED,
    IngestionRunState.EXTRACTING,
    IngestionRunState.EXTRACTED,
    IngestionRunState.CHUNKING,
    IngestionRunState.ENRICHING,
    IngestionRunState.EMBEDDING,
    IngestionRunState.INDEXING,
    IngestionRunState.VALIDATING,
    IngestionRunState.PUBLISHED,
]


def test_broker_is_list_queue_broker():
    from taskiq_redis import ListQueueBroker

    assert isinstance(broker, ListQueueBroker)


def test_ingestion_task_is_registered():
    assert run_ingestion_stage.task_name.endswith("run_ingestion_stage")
    assert run_ingestion_stage.broker is broker


class FakeRuns:
    """进程内 IngestionRunRepository（含 run 元数据）。"""

    def __init__(self) -> None:
        self._state: dict[str, IngestionRunState] = {}
        self._meta: dict[str, dict[str, object]] = {}

    async def create_run(self, document_id: str, workspace_id: str) -> str:
        run_id = "run-1"
        self._state[run_id] = IngestionRunState.ACCEPTED
        self._meta[run_id] = {
            "document_id": document_id,
            "workspace_id": workspace_id,
            "object_key": "raw.md",
            "title": "测试文档",
        }
        return run_id

    async def state(self, run_id: str) -> IngestionRunState:
        return self._state[run_id]

    async def complete_stage(self, run_id: str, stage: IngestionRunState) -> IngestionRunState:
        order = list(_STAGES)
        idx = order.index(stage)
        nxt = order[idx + 1] if idx + 1 < len(order) else stage
        self._state[run_id] = nxt
        return nxt

    async def set_metadata(self, run_id: str, key: str, value: object) -> None:
        self._meta[run_id][key] = value

    async def metadata(self, run_id: str) -> dict[str, object]:
        return self._meta[run_id]


class FakeDocuments:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    async def create(self, document: Document) -> Document:
        self._docs[document.id] = document
        return document

    async def get(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    async def list_for_knowledge_base(self, kb_id: str):
        return ()

    async def update_state(self, document_id: str, state: IngestionRunState) -> None:
        doc = self._docs[document_id]
        self._docs[document_id] = Document(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            workspace_id=doc.workspace_id,
            title=doc.title,
            format=doc.format,
            size_bytes=doc.size_bytes,
            ingestion_state=state,
            chunk_count=doc.chunk_count,
            published=doc.published,
        )

    async def set_published(self, document_id: str, published: bool) -> None:
        doc = self._docs[document_id]
        self._docs[document_id] = Document(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            workspace_id=doc.workspace_id,
            title=doc.title,
            format=doc.format,
            size_bytes=doc.size_bytes,
            ingestion_state=doc.ingestion_state,
            chunk_count=doc.chunk_count,
            published=published,
        )

    async def delete(self, document_id: str) -> None:
        self._docs.pop(document_id, None)

    async def list_ids(self) -> tuple[str, ...]:
        return tuple(self._docs)


class FakeStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = dict(objects)

    async def put(self, workspace_id: str, data: bytes, *, content_type: str):
        from medicalrag_core.storage.ports import ObjectRef

        key = f"obj-{len(self._objects)}"
        self._objects[key] = data
        return ObjectRef(workspace_id=workspace_id, key=key)

    async def get(self, ref):
        return self._objects[ref.key]


class FakeChunks:
    def __init__(self) -> None:
        self._chunks: list[ChunkRecord] = []

    async def insert_many(self, chunks: tuple[ChunkRecord, ...]) -> None:
        self._chunks.extend(chunks)

    async def list_for_document(self, document_id: str) -> tuple[ChunkRecord, ...]:
        return tuple(c for c in self._chunks if c.document_id == document_id)

    async def count_for_document(self, document_id: str) -> int:
        return len([c for c in self._chunks if c.document_id == document_id])


class FakeContextualizer:
    """背景补写 fake：记录调用并返回确定性背景。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def situate(self, *, document_title, heading_path, chunk_text, preceding_text):
        self.calls.append(chunk_text)
        return f"背景：{document_title}的{' > '.join(heading_path)}部分"


class FakeEmbeddings:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3]] * len(texts)


class FakeIndexer:
    def __init__(self, dim: int | None = 1536) -> None:
        self.calls: list[dict] = []
        self.points: dict[str, list[str]] = {}
        self.dim = dim
        self.eligibility: dict[str, bool] = {}

    async def index(
        self,
        document_id,
        workspace_id,
        chunks,
        *,
        title,
        source_id,
        dense_vectors,
        embedding_texts=None,
    ):
        self.calls.append(
            {
                "document_id": document_id,
                "workspace_id": workspace_id,
                "chunk_count": len(chunks),
                "title": title,
                "dense_vectors": list(dense_vectors),
                "embedding_texts": list(embedding_texts or []),
            }
        )
        self.points[document_id] = [c.text for c in chunks]

    async def set_eligibility(self, document_id: str, eligible: bool) -> None:
        self.eligibility[document_id] = eligible

    async def count_points(self, document_id: str) -> int:
        return len(self.points.get(document_id, []))

    async def read_point_snippets(self, document_id: str, limit: int = 8) -> tuple[str, ...]:
        return tuple(self.points.get(document_id, [])[:limit])

    async def dense_dim(self) -> int | None:
        return self.dim


class FakeMinerU:
    """官方批量上传流 fake：申请 URL → PUT 字节 → 批次 done → ZIP artifact。"""

    def __init__(self, artifact: bytes, *, status: str = "done") -> None:
        self.artifact = artifact
        self.status = status
        self.uploaded: bytes | None = None

    async def request_file_upload(self, filename: str) -> tuple[str, str]:
        return ("batch-1", "https://mineru.example/upload")

    async def upload_bytes(self, upload_url: str, content: bytes) -> None:
        self.uploaded = content

    async def batch_status(self, batch_id: str) -> str:
        return self.status

    async def download_results(self, batch_id: str) -> bytes:
        return self.artifact


_RAW_MD = "血压 >=140/90 mmHg 为高血压诊断界值。\n降压目标 <140/90。".encode()


def _make_service(**overrides):
    deps = {
        "runs": FakeRuns(),
        "documents": FakeDocuments(),
        "storage": FakeStorage({"raw.md": _RAW_MD}),
        "chunks": FakeChunks(),
        "embeddings": FakeEmbeddings(),
        "indexer": FakeIndexer(),
        "mineru": None,
        "contextualizer": None,
    }
    deps.update(overrides)
    return IngestionService(IngestionDeps(**deps))


async def test_md_pipeline_runs_to_published():
    service = _make_service()
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-1",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="测试.md",
        format=".md",
        size_bytes=64,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")

    state = IngestionRunState.ACCEPTED
    for stage in _STAGES:
        state = await service.run(run_id, stage)
    assert state is IngestionRunState.PUBLISHED
    assert (await docs.get(document.id)).ingestion_state is IngestionRunState.PUBLISHED
    # ADR 0079：发布翻转 PG 资格与索引点资格
    assert (await docs.get(document.id)).published is True
    assert service._deps.indexer.eligibility[document.id] is True
    assert await service._deps.chunks.count_for_document(document.id) >= 1
    assert len(service._deps.indexer.calls) == 1
    assert service._deps.indexer.calls[0]["document_id"] == "doc-1"


async def test_multimodal_without_mineru_fails_deterministically():
    service = _make_service()  # mineru=None
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-2",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="报告.pdf",
        format=".pdf",
        size_bytes=1024,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")
    await service.run(run_id, IngestionRunState.ACCEPTED)  # 推进到 EXTRACTING
    with pytest.raises(ExtractionError):
        await service.run(run_id, IngestionRunState.EXTRACTING)


def _mineru_zip(markdown: str) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("analysis/full.md", markdown)
    return buffer.getvalue()


async def test_multimodal_mineru_file_upload_publishes_markdown_sections():
    markdown = "# 诊断标准\n收缩压 >=140 mmHg。\n# 治疗目标\n降压目标 <140/90。"
    mineru = FakeMinerU(_mineru_zip(markdown))
    service = _make_service(
        mineru=mineru,
        storage=FakeStorage({"guide.pdf": b"%PDF-fake-bytes"}),
    )
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-pdf",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="指南.pdf",
        format=".pdf",
        size_bytes=2048,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")
    await runs.set_metadata(run_id, "object_key", "guide.pdf")

    state = IngestionRunState.ACCEPTED
    for stage in _STAGES:
        state = await service.run(run_id, stage)

    assert state is IngestionRunState.PUBLISHED
    assert mineru.uploaded == b"%PDF-fake-bytes"
    chunks = await service._deps.chunks.list_for_document(document.id)
    assert [c.headings for c in chunks] == [("诊断标准",), ("治疗目标",)]
    # token 计数来自 tokenizer（非空格切分），中文文本计数 > 空格词数
    assert all(c.token_count > len(c.text.split()) for c in chunks)


async def test_validating_fails_on_schema_dim_mismatch():
    service = _make_service(indexer=FakeIndexer(dim=999))
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-dim",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="a.md",
        format=".md",
        size_bytes=16,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")
    for stage in _STAGES[:7]:  # 推进到 INDEXING 完成
        await service.run(run_id, stage)
    with pytest.raises(ExtractionError):
        await service.run(run_id, IngestionRunState.VALIDATING)


async def test_contextual_background_feeds_embedding_and_index_texts():
    contextualizer = FakeContextualizer()
    service = _make_service(contextualizer=contextualizer)
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-ctx",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="测试.md",
        format=".md",
        size_bytes=64,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")
    state = IngestionRunState.ACCEPTED
    for stage in _STAGES:
        state = await service.run(run_id, stage)
    assert state is IngestionRunState.PUBLISHED

    # 背景按文档顺序逐块生成，且同时进入 embedding 与 indexing 的同源文本（ADR 0078）
    assert len(contextualizer.calls) >= 1
    texts = service._deps.indexer.calls[0]["embedding_texts"]
    assert texts and all(t.startswith("背景：") for t in texts)


async def test_advance_run_enqueues_next_stage_until_terminal():
    service = _make_service()
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-3",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="a.md",
        format=".md",
        size_bytes=16,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")

    kicked: list[IngestionRunState] = []

    async def fake_kick(run_id: str, stage: IngestionRunState) -> None:
        kicked.append(stage)

    stage = IngestionRunState.ACCEPTED
    while not is_terminal(await advance_run(service, fake_kick, run_id, stage)):
        stage = kicked[-1]

    assert kicked == [
        IngestionRunState.EXTRACTING,
        IngestionRunState.EXTRACTED,
        IngestionRunState.CHUNKING,
        IngestionRunState.ENRICHING,
        IngestionRunState.EMBEDDING,
        IngestionRunState.INDEXING,
        IngestionRunState.VALIDATING,
    ]  # 每阶段之后投递下一阶段，PUBLISHED 终止不再投递
