"""TaskIQ Worker 组合根与 9 阶段摄取流水线行为测试（覆盖 Markdown/TXT 原生解析全流程）。"""

import pytest

from medicalrag_core.ingestion.chunks import ChunkRecord
from medicalrag_core.ingestion.knowledge import Document
from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_worker.ingestion import ExtractionError, IngestionDeps, IngestionService
from medicalrag_worker.worker import DELAY_QUEUE, advance_run, broker, run_ingestion_stage

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


def test_broker_uses_rabbitmq_with_dead_letter_and_delay_queue():
    """传输层为 RabbitMQ（ADR 0086）：持久化 quorum 队列 + 延迟队列 + 两层中间件。

    只钉**我们自己的配置**（模块常量与 broker 公开表面）；不拿适配器私有属性
    （``_qos``/``_delay_queue``/``_dead_letter_queue``）做断言：库内改名会误红，
    换成同名类又会假绿。真实投递/重投不在本层（见 docs/testing-seams.md）。
    """
    from taskiq.middlewares.smart_retry_middleware import SmartRetryMiddleware
    from taskiq_aio_pika import AioPikaBroker, Queue

    from medicalrag_worker.worker import IngestionFailureMiddleware

    assert isinstance(broker, AioPikaBroker)
    # 延迟队列属性即我们的配置：重投的 delay 标签经此队列过期死信回主队列（TTL 延迟语义）
    assert DELAY_QUEUE.name == "taskiq.delay"
    assert DELAY_QUEUE.durable is True
    assert DELAY_QUEUE.type.value == "quorum"
    # 任务队列沿用适配器默认声明：钉「持久化 quorum」契约——库默认若变更即失败，提示重评耐久性
    default_task_queue = Queue()
    assert default_task_queue.durable is True
    assert default_task_queue.type.value == "quorum"
    assert len(broker.middlewares) == 2
    assert isinstance(broker.middlewares[0], SmartRetryMiddleware)
    assert isinstance(broker.middlewares[1], IngestionFailureMiddleware)


def test_ingestion_task_declares_retry_labels():
    # 任务名是运维在队列里看到的标识，改名会打断排障与告警
    assert run_ingestion_stage.task_name.endswith("run_ingestion_stage")
    # SmartRetryMiddleware 默认 default_retry_label=False：不显式声明标签则根本不重试
    assert run_ingestion_stage.labels["retry_on_error"] is True
    assert run_ingestion_stage.labels["max_retries"] == 3


async def test_failure_middleware_marks_run_failed_only_after_retries_exhausted(monkeypatch):
    from taskiq import TaskiqMessage, TaskiqResult

    import medicalrag_worker.worker as worker

    marked: list[tuple[str, str]] = []

    class FakeIngestion:
        async def mark_failed(self, run_id: str, reason: str) -> None:
            marked.append((run_id, reason))

    class FakeRepos:
        ingestion = FakeIngestion()

    monkeypatch.setattr(worker, "_repos", FakeRepos())
    middleware = worker.IngestionFailureMiddleware()
    result = TaskiqResult(is_err=True, return_value=None, execution_time=0.0)

    def _message(retries: str) -> TaskiqMessage:
        return TaskiqMessage(
            task_id="t1",
            task_name=run_ingestion_stage.task_name,
            labels={"_retries": retries, "max_retries": "3"},
            args=["run-1"],
            kwargs={},
        )

    # 还有重试机会：不标记终态
    await middleware.on_error(_message("0"), result, RuntimeError("boom"))
    assert marked == []
    # 重试耗尽：标记 FAILED 并记录异常类型
    await middleware.on_error(_message("2"), result, RuntimeError("boom"))
    assert marked == [("run-1", "RuntimeError")]

    # 其他任务（非摄取阶段）不受影响
    other = _message("2").model_copy(update={"task_name": "medicalrag_worker.worker:relay_outbox"})
    await middleware.on_error(other, result, RuntimeError("boom"))
    assert len(marked) == 1


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

    async def mark_failed(self, run_id: str, reason: str) -> None:
        """与 SqlIngestionRunRepository.mark_failed 同语义：记录失败阶段并置 FAILED。"""
        data = self._meta[run_id]
        data["failure_reason"] = reason
        data["failed_stage"] = self._state[run_id].value
        self._state[run_id] = IngestionRunState.FAILED

    async def resume_failed(self, run_id: str, stage: IngestionRunState) -> bool:
        """与 SqlIngestionRunRepository.resume_failed 同语义：仅失败阶段一致时复位。"""
        if self._state[run_id] is not IngestionRunState.FAILED:
            return False
        if str(self._meta[run_id].get("failed_stage", "")) != stage.value:
            return False
        self._state[run_id] = stage
        return True


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

    async def set_chunk_count(self, document_id: str, count: int) -> None:
        doc = self._docs[document_id]
        self._docs[document_id] = Document(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            workspace_id=doc.workspace_id,
            title=doc.title,
            format=doc.format,
            size_bytes=doc.size_bytes,
            ingestion_state=doc.ingestion_state,
            chunk_count=count,
            published=doc.published,
        )
        self.chunk_count = count

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

    async def delete_for_document(self, document_id: str) -> None:
        self._chunks = [c for c in self._chunks if c.document_id != document_id]

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
    def __init__(self, dim: int | None = 3) -> None:  # 默认对齐 FakeEmbeddings 的 3 维伪向量
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


class FakeGate:
    """MinerU 并发闸伪实现（ADR 0087）：结构化匹配 IngestionDeps.mineru_gate 端口，记录调用。"""

    def __init__(self, granted: bool = True) -> None:
        self.granted = granted
        self.acquire_calls: list[tuple[str, int, str]] = []
        self.released: list[str] = []

    async def acquire(self, name, *, limit, holder, wait_s):
        self.acquire_calls.append((name, limit, holder))
        return self.granted

    async def release(self, name, holder):
        self.released.append(holder)


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

    async def download_results_to(self, batch_id: str, dest) -> None:
        with open(dest, "wb") as handle:  # noqa: ASYNC230  # 进程内伪件，无真实磁盘 I/O
            handle.write(self.artifact)


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
        # 与 FakeEmbeddings 的伪向量维度一致（逐条维度校验按此比对）
        "embedding_dim": 3,
        "mineru_concurrency": 2,
    }
    deps.update(overrides)
    return IngestionService(IngestionDeps(**deps))


async def test_service_resume_failed_reruns_failed_stage_only():
    """运营台重放语义：FAILED Run 复位到记录的失败阶段续跑，而非从头重摄；
    请求阶段与失败阶段不一致时拒绝复位（返回 FAILED 不执行）。"""
    service = _make_service()
    runs = service._deps.runs
    docs = service._deps.documents
    document = Document(
        id="doc-4",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="a.md",
        format=".md",
        size_bytes=16,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await runs.create_run(document.id, "ws-1")
    await service.run(run_id, IngestionRunState.ACCEPTED)  # extracting 完成 → EXTRACTING
    await runs.mark_failed(run_id, "boom")  # 假设 EXTRACTING 阶段失败
    assert await runs.state(run_id) is IngestionRunState.FAILED

    # 阶段错位的重放请求：不复位、不执行
    state = await service.run(run_id, IngestionRunState.CHUNKING)
    assert state is IngestionRunState.FAILED

    # 与失败阶段一致的重放：复位后续跑推进
    state = await service.run(run_id, IngestionRunState.EXTRACTING)
    assert state is IngestionRunState.EXTRACTED


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
    # 发布翻转 PG 资格与索引点资格
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


def test_strip_image_links_removes_mineru_relative_assets():
    """A-1（ADR 0087）：MinerU markdown 的相对图片链接在分块前剥离，不成为向量垃圾 token。"""
    from medicalrag_worker.ingestion import _strip_image_links

    raw = "# 指南\n\n![图](images/abc.jpg)\n\n血压测量方法。\n\n![](images/x.png)结尾文字"
    cleaned = _strip_image_links(raw)
    assert "![" not in cleaned
    assert "images/" not in cleaned
    assert "血压测量方法。" in cleaned
    assert "结尾文字" in cleaned


async def test_mineru_artifact_images_are_stripped_from_sections(tmp_path):
    """A-1（ADR 0087）：zip 产物路径同样剥离图片链接后才进入章节切分。"""
    import io
    import zipfile

    from medicalrag_worker.ingestion import _normalize_mineru_sections

    md = "# 指南\n\n![图](images/a.jpg)\n\n血压测量方法。\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as bundle:
        bundle.writestr("artifact/full.md", md)
        bundle.writestr("artifact/images/a.jpg", b"\x89PNG")
    path = tmp_path / "artifact.zip"
    path.write_bytes(buf.getvalue())

    sections = _normalize_mineru_sections(path)
    assert len(sections) == 1
    assert "![" not in sections[0].text
    assert "images/a.jpg" not in sections[0].text
    assert "血压测量方法。" in sections[0].text


async def test_mineru_extraction_acquires_and_releases_concurrency_gate():
    """A-2（ADR 0087）：MinerU 解析段在并发闸内执行，成功后必须释放槽位。"""
    gate = FakeGate()
    service = _make_service(mineru=FakeMinerU(_RAW_MD), mineru_gate=gate)
    docs = service._deps.documents
    document = Document(
        id="doc-5",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="指南.pdf",
        format=".pdf",
        size_bytes=64,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await service._deps.runs.create_run(document.id, "ws-1")
    await service.run(run_id, IngestionRunState.ACCEPTED)  # 检查点阶段

    state = await service.run(run_id, IngestionRunState.EXTRACTING)  # 实际提取（闸门内）
    assert state is IngestionRunState.EXTRACTED
    assert gate.acquire_calls == [("mineru", 2, run_id)]
    assert gate.released == [run_id]


async def test_mineru_gate_denial_raises_retryable_extraction_error():
    """A-2（ADR 0087）：排队预算内未取得解析额度 → 可重试失败（TaskIQ 退避接管），不泄漏槽位。"""
    gate = FakeGate(granted=False)
    service = _make_service(mineru=FakeMinerU(_RAW_MD), mineru_gate=gate)
    docs = service._deps.documents
    document = Document(
        id="doc-6",
        knowledge_base_id="kb-1",
        workspace_id="ws-1",
        title="指南.pdf",
        format=".pdf",
        size_bytes=64,
        ingestion_state=IngestionRunState.ACCEPTED,
    )
    await docs.create(document)
    run_id = await service._deps.runs.create_run(document.id, "ws-1")
    await service.run(run_id, IngestionRunState.ACCEPTED)  # 检查点阶段

    with pytest.raises(ExtractionError):
        await service.run(run_id, IngestionRunState.EXTRACTING)
    assert gate.released == []


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

    # 背景按文档顺序逐块生成，且同时进入 embedding 与 indexing 的同源文本
    assert len(contextualizer.calls) >= 1
    texts = service._deps.indexer.calls[0]["embedding_texts"]
    assert texts and all(t.startswith("背景：") for t in texts)


async def test_advance_run_kicks_publish_stage_until_no_further_work():
    """回归（P0）：PUBLISHED 虽为终态但发布收尾（published/eligibility 翻转）必须被执行；
    PUBLISHED 阶段自返时不再投递（否则同一稳定任务 ID 会无限循环重投），FAILED 同样终止投递。"""
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
    while True:
        before = len(kicked)
        await advance_run(service, fake_kick, run_id, stage)
        if len(kicked) == before:  # 无新投递：到达没有后续工作的状态
            break
        stage = kicked[-1]

    assert kicked == [
        IngestionRunState.EXTRACTING,
        IngestionRunState.EXTRACTED,
        IngestionRunState.CHUNKING,
        IngestionRunState.ENRICHING,
        IngestionRunState.EMBEDDING,
        IngestionRunState.INDEXING,
        IngestionRunState.VALIDATING,
        IngestionRunState.PUBLISHED,
    ]  # 每阶段之后投递下一阶段，含 PUBLISHED 发布收尾；收尾自返后停止
    # 经 advance_run 驱动的完整链路：文档确实发布且向量检索资格已激活（回归锁定 P0 语义）
    assert (await docs.get(document.id)).published is True
    assert service._deps.indexer.eligibility[document.id] is True
