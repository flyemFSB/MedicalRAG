"""文档摄取流水线执行服务（实现 9 阶段状态流转）。

每个阶段对应专门的执行器方法：先执行本阶段具体的幂等工作，再调用 `complete_stage` 执行单向状态推进；
返回推进后的阶段状态，由 TaskIQ 后台任务根据新状态自动调度下一阶段作业。
摄取作业级别的运行时上下文与中间生成产物（如 object_key、artifact_ref、分块数量、稠密向量索引等）统一持久化于 IngestionRun 元数据中。

9 阶段职责划分：
  extracting  —— 读取原始文件对象 → 解析出 Section 章节（多模态/PDF 走 MinerU 复杂版面分析，.md/.txt 走原生结构化解析）→ 持久化解析产物 artifact
  extracted   —— 阶段检查点（确认 artifact 已安全持久化存储）
  chunking    —— 读取 artifact → 执行结构感知分块 chunk_document → 写入分块记录 ChunkRecord
  enriching   —— 可选增强：调用外部模型执行分块上下文背景补写，生成结果写入 IngestionRun 元数据
  embedding   —— 批量调用向量嵌入 Provider（基于背景增强富文本），将 float32 稠密向量以紧凑字节流写入对象存储
  indexing    —— 读取预计算好的稠密向量及同源富文本，upsert 写入 Qdrant 集合并同步更新文档的分块总数
  validating  —— 严格校验实际索引点数、分块内容校验和 SHA256 及向量维度模式；校验未通过则抛出异常进入 FAILED 状态
  published   —— 更新文档发布状态为 PUBLISHED（终态）并激活向量点的检索可见性
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
import zipfile
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.chunking.chunking import Section, chunk_document, embedding_text
from medicalrag_core.ids import uuid7
from medicalrag_core.ingestion.chunks import ChunkRecord, ChunkRepository
from medicalrag_core.ingestion.enrichment import Contextualizer
from medicalrag_core.ingestion.knowledge import DocumentRepository
from medicalrag_core.ingestion.ports import IngestionRunRepository
from medicalrag_core.ingestion.state_machine import (
    IngestionRunState,
    is_terminal,
    precedes,
)
from medicalrag_core.ingestion.validation import validate_index
from medicalrag_core.retrieval.ports import EmbeddingProvider, VectorIndexer
from medicalrag_core.storage.ports import ObjectRef, ObjectStorage
from medicalrag_infra.logging import logger
from medicalrag_infra.providers.mineru import MinerUClient
from medicalrag_infra.ratelimit import RedisConcurrencyGate
from medicalrag_infra.tokens import count_tokens


@dataclass(frozen=True, slots=True)
class IngestionDeps:
    """摄取流水线运行所需的全部依赖适配器（由组合根负责组装注入；单元测试可注入内存伪实现）。"""

    runs: IngestionRunRepository
    documents: DocumentRepository
    storage: ObjectStorage
    chunks: ChunkRepository
    embeddings: EmbeddingProvider
    indexer: VectorIndexer
    # 并发闸与额度由组合根成对注入（RedisConcurrencyGate 即 infra 唯一实现，测试注入伪实现）
    mineru_concurrency: int
    mineru: MinerUClient | None = None
    contextualizer: Contextualizer | None = None
    embedding_dim: int = 1536
    mineru_gate: RedisConcurrencyGate | None = None


class ExtractionError(RuntimeError):
    """文档解析提取或验证阶段异常；重试耗尽后作业状态将被置为 FAILED（异常重放机制）。"""


class IngestionService:
    """驱动文档摄取作业从 accepted 阶段平稳推进至 published 终态的确定性业务编排服务。"""

    def __init__(self, deps: IngestionDeps) -> None:
        self._deps = deps

    async def run(self, run_id: str, stage: IngestionRunState) -> IngestionRunState:
        """执行指定摄取阶段的核心业务逻辑并推进状态；返回推进后的新状态（若已达终止状态则不再继续推进）。

        PUBLISHED 虽然为终态，但仍包含更新文档状态的收尾操作：先执行业务操作再返回终态，
        不再调用 complete_stage（终态禁止再次触发状态跃迁）。

        - FAILED 复位重放：请求阶段与记录的失败阶段一致时复位后重跑（运营台 retry 语义）；
        - 滞后阶段重复投递（at-least-once）：目标阶段已完成时按幂等成功处理，返回当前状态。
        """
        current = await self._deps.runs.state(run_id)
        if stage is IngestionRunState.PUBLISHED:
            if current is not IngestionRunState.PUBLISHED:
                raise ValueError(f"摄取阶段错位: 当前处于 {current} 状态，请求执行 {stage}")
            await self._published(run_id)
            return IngestionRunState.PUBLISHED
        if current is IngestionRunState.FAILED:
            resumed = await self._deps.runs.resume_failed(run_id, stage)
            if not resumed:
                return IngestionRunState.FAILED
            current = stage
        elif is_terminal(current):
            return current
        elif stage is not current:
            if precedes(stage, current):
                # 重复投递的滞后阶段：阶段工作早已完成并越过，按幂等成功返回当前状态
                logger.debug("摄取运行阶段消息重复投递（已越过当前阶段，执行幂等跳过）：run_id={} stage={}", run_id, stage)
                return current
            raise ValueError(f"摄取阶段错位: 当前处于 {current} 状态，请求执行 {stage}")
        if stage is IngestionRunState.EXTRACTING:
            await self._extracting(run_id)
        elif stage is IngestionRunState.CHUNKING:
            await self._chunking(run_id)
        elif stage is IngestionRunState.ENRICHING:
            await self._enriching(run_id)
        elif stage is IngestionRunState.EMBEDDING:
            await self._embedding(run_id)
        elif stage is IngestionRunState.INDEXING:
            await self._indexing(run_id)
        elif stage is IngestionRunState.VALIDATING:
            await self._validating(run_id)
        # EXTRACTED 为检查点阶段：无额外的独立业务逻辑
        return await self._deps.runs.complete_stage(run_id, stage)

    # --- 各阶段具体执行器 ---

    async def _extracting(self, run_id: str) -> None:
        meta = await self._deps.runs.metadata(run_id)
        document_id = str(meta["document_id"])
        document = await self._deps.documents.get(document_id)
        if document is None:
            raise ExtractionError("文档不存在")
        ref = ObjectRef(workspace_id=str(meta["workspace_id"]), key=str(meta["object_key"]))
        raw = await self._deps.storage.get(ref)
        sections, checksum = await self._extract(run_id, document.format, raw, meta)
        artifact_ref = await self._deps.storage.put(
            str(meta["workspace_id"]),
            json.dumps(
                [{"level": s.level, "heading": s.heading, "text": s.text} for s in sections],
                ensure_ascii=False,
            ).encode("utf-8"),
            content_type="application/json",
        )
        await self._deps.runs.set_metadata(run_id, "artifact_ref", artifact_ref.key)
        await self._deps.runs.set_metadata(run_id, "checksum", checksum)

    async def _extract(
        self, run_id: str, fmt: str, raw: bytes, meta: dict[str, object]
    ) -> tuple[tuple[Section, ...], str]:
        """复杂/多模态文档接入 MinerU 提取，.md/.txt 纯文本执行原生结构化提取。

        走官方预签名上传地址（申请上传链接 → PUT 上传文件字节流 → 服务端自动启动解析任务 → 轮询批次状态）。
        若解析失败则抛出 ExtractionError，由工作流置入 FAILED 状态（供管理后台重试）。
        """
        checksum = hashlib.sha256(raw).hexdigest()
        if fmt in {".md", ".txt"}:
            text = raw.decode("utf-8", errors="replace")
            return (Section(level=1, heading="正文", text=text),), checksum
        if self._deps.mineru is None:
            raise ExtractionError(f"多模态/复杂版面格式 {fmt} 需要启用 MinerU 解析器")
        # 分布式并发闸：预算内排队等待解析额度（跨进程限制并发任务数），超时按可重试失败处理
        gate = self._deps.mineru_gate
        if gate is not None:
            granted = await gate.acquire(
                "mineru", limit=self._deps.mineru_concurrency, holder=run_id, wait_s=30.0
            )
            if not granted:
                raise ExtractionError("MinerU 解析并发额度已占满，请稍后重试")
        try:
            filename = str(meta.get("title") or f"document{fmt}")
            batch_id, upload_url = await self._deps.mineru.request_file_upload(filename)
            await self._deps.mineru.upload_bytes(upload_url, raw)
            status = await self._poll_batch(run_id, batch_id)
            if status != "done":
                raise ExtractionError(f"MinerU 批次解析未成功完成: {status}")
            # 成果 ZIP 流式落盘至临时文件（不整包载入内存）；解析完成后随临时目录一并清理
            with tempfile.TemporaryDirectory() as tmp_dir:
                artifact_path = Path(tmp_dir) / "artifact.zip"
                await self._deps.mineru.download_results_to(batch_id, artifact_path)
                return _normalize_mineru_sections(artifact_path), checksum
        finally:
            if gate is not None:
                await gate.release("mineru", run_id)

    async def _poll_batch(
        self,
        run_id: str,
        batch_id: str,
        *,
        attempts: int = 90,
        interval_s: float = 2.0,
        max_interval_s: float = 10.0,
    ) -> str:
        """有界轮询批次解析状态（间隔指数退避）；若超时则返回最新状态，由上层决策重试或转入 FAILED 状态。

        每轮将最新批次状态写入 Run 元数据：既是进度可观测，也刷新 updated_at——
        轮询总时长可达约 15 分钟，若无任何 DB 写入会被 fail_stale_runs 僵尸自愈误杀（执行中置 FAILED）。
        """
        mineru = self._deps.mineru
        assert mineru is not None  # _extract 已判定复杂文档必须具备 MinerU 客户端
        status = "pending"
        for attempt in range(attempts):
            status = await mineru.batch_status(batch_id)
            await self._deps.runs.set_metadata(run_id, "mineru_batch_status", status)
            if status in {"done", "failed"}:
                return status
            # 指数退避：2s 起步，逐次上浮至上限，减少对 MinerU API 的无效压力
            await asyncio.sleep(min(interval_s * (1.5**attempt), max_interval_s))
        return status

    async def _chunking(self, run_id: str) -> None:
        meta = await self._deps.runs.metadata(run_id)
        artifact_ref = ObjectRef(
            workspace_id=str(meta["workspace_id"]), key=str(meta["artifact_ref"])
        )
        payload = json.loads((await self._deps.storage.get(artifact_ref)).decode("utf-8"))
        sections = tuple(
            Section(level=s["level"], heading=s["heading"], text=s["text"]) for s in payload
        )
        document_id = str(meta["document_id"])
        chunks = chunk_document(document_id, sections, count_tokens=count_tokens)
        # 先删后建：重摄/断点续跑时清理旧切片，避免主键冲突与残留
        await self._deps.chunks.delete_for_document(document_id)
        await self._deps.chunks.insert_many(
            tuple(
                ChunkRecord(
                    id=str(uuid7()),
                    document_id=document_id,
                    workspace_id=str(meta["workspace_id"]),
                    text=c.text,
                    headings=c.heading_path,
                    index=c.index,
                    checksum=hashlib.sha256(c.text.encode()).hexdigest(),
                    token_count=count_tokens(c.text),
                )
                for c in chunks
            )
        )
        await self._deps.runs.set_metadata(run_id, "expected_chunks", len(chunks))

    async def _enriching(self, run_id: str) -> None:
        """文档分块背景补写阶段：按正文顺序为各分块生成定位与上下文背景。

        若未配置 Contextualizer 或单分块生成失败，则该分块保持无背景说明（优雅降级不阻断，不编造虚假背景）。
        """
        if self._deps.contextualizer is None:
            return
        meta = await self._deps.runs.metadata(run_id)
        document_id = str(meta["document_id"])
        document = await self._deps.documents.get(document_id)
        title = str(meta.get("title") or (document.title if document else document_id))
        chunks = await self._deps.chunks.list_for_document(document_id)
        contexts: dict[str, str] = {}
        preceding = ""
        for record in chunks:
            try:
                context = await self._deps.contextualizer.situate(
                    document_title=title,
                    heading_path=record.headings,
                    chunk_text=record.text,
                    preceding_text=preceding,
                )
            except ProviderUnavailableError:
                context = ""
            contexts[record.id] = context
            preceding = record.text
            # 逐分块增量落盘：既作为分块级检查点，也用于刷新 updated_at 时间戳——
            # 大文档逐分块串行调用外部模型可能耗时较长，若无数据库写入会被超时自愈机制判定为僵尸运行
            await self._deps.runs.set_metadata(run_id, "chunk_context", contexts)

    def _composed_texts(
        self, chunks: tuple[ChunkRecord, ...], meta: dict[str, object]
    ) -> list[str]:
        """向量嵌入与索引构建共用的完整富文本：背景增强说明 + 标题路径 + 正文原文。"""
        raw = cast(dict[str, object], meta.get("chunk_context") or {})
        contexts: dict[str, str] = {str(k): str(v) for k, v in raw.items()}
        texts: list[str] = []
        for record in chunks:
            base = embedding_text(_to_chunk(record))
            context = contexts.get(record.id, "")
            texts.append(f"{context}\n{base}" if context else base)
        return texts

    async def _embedding(self, run_id: str) -> None:
        meta = await self._deps.runs.metadata(run_id)
        chunks = await self._deps.chunks.list_for_document(str(meta["document_id"]))
        texts = self._composed_texts(chunks, meta)
        vectors: list[Sequence[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = await self._deps.embeddings.embed(texts[start : start + _EMBED_BATCH])
            # 逐条维度校验：嵌入模型输出与集合物理维度不符时立即失败，
            # 报错明确指出双方维度，而不是让错误向量在 Qdrant upsert 处炸出难懂的服务端错误
            for position, vector in enumerate(batch):
                if len(vector) != self._deps.embedding_dim:
                    raise ExtractionError(
                        f"嵌入模型输出 {len(vector)} 维，与集合要求的 {self._deps.embedding_dim} 维不符"
                        f"（第 {start + position} 个分块）"
                    )
            vectors.extend(batch)
        # 稠密向量以紧凑 float32 字节流持久化至对象存储中，避免占用 PostgreSQL 关系库元数据大字段
        ref = await self._deps.storage.put(
            str(meta["workspace_id"]),
            _encode_vectors(vectors),
            content_type="application/octet-stream",
        )
        await self._deps.runs.set_metadata(run_id, "vectors_ref", ref.key)

    async def _indexing(self, run_id: str) -> None:
        meta = await self._deps.runs.metadata(run_id)
        document_id = str(meta["document_id"])
        chunks = await self._deps.chunks.list_for_document(document_id)
        vectors_ref = meta.get("vectors_ref")
        if not vectors_ref:
            raise ExtractionError("缺失向量嵌入计算产物（vectors_ref）")
        vectors = _decode_vectors(
            await self._deps.storage.get(
                ObjectRef(workspace_id=str(meta["workspace_id"]), key=str(vectors_ref))
            )
        )
        await self._deps.indexer.index(
            document_id,
            str(meta["workspace_id"]),
            tuple(_to_chunk(c) for c in chunks),
            title=str(meta.get("title", document_id)),
            source_id=document_id,
            dense_vectors=vectors,
            embedding_texts=self._composed_texts(chunks, meta),
        )

    async def _validating(self, run_id: str) -> None:
        """发布门禁阶段：校验真实索引状态与数据一致性。

        - 分块数量校验：比对 Qdrant 集合中实际就绪的向量点数（而非单纯依赖关系库记录数）；
        - 内容完整性校验：抽样回读索引点的 payload text 并重新计算 SHA256 校验和，与关系库记录比对；
        - 向量维度一致性校验：确认向量集合当前的 dense 维度与系统配置的向量维度完全一致。
        """
        meta = await self._deps.runs.metadata(run_id)
        document_id = str(meta["document_id"])
        records = await self._deps.chunks.list_for_document(document_id)
        checksums = {record.checksum for record in records}
        indexed_points = await self._deps.indexer.count_points(document_id)
        sampled = await self._deps.indexer.read_point_snippets(document_id)
        checksum_ok = all(
            hashlib.sha256(text.encode()).hexdigest() in checksums for text in sampled
        )
        dim = await self._deps.indexer.dense_dim()
        validation = validate_index(
            expected_chunks=int(cast(int, meta.get("expected_chunks", 0))),
            indexed_chunks=indexed_points,
            checksum_ok=checksum_ok,
            active_schema=dim == self._deps.embedding_dim,
        )
        if not validation.passed:
            raise ExtractionError("；".join(validation.reasons))

    async def _published(self, run_id: str) -> None:
        meta = await self._deps.runs.metadata(run_id)
        document_id = str(meta["document_id"])
        await self._deps.documents.update_state(
            str(meta["document_id"]), IngestionRunState.PUBLISHED
        )
        await self._deps.documents.set_chunk_count(
            document_id, int(cast(int, meta.get("expected_chunks", 0)))
        )
        # 唯有在发布门禁全部验证通过后，方可激活向量索引中的检索可见资格
        await self._deps.documents.set_published(document_id, True)
        await self._deps.indexer.set_eligibility(document_id, True)


_EMBED_BATCH = 64  # 固定批处理切片大小


def _encode_vectors(vectors: Sequence[Sequence[float]]) -> bytes:
    """将浮点向量紧凑序列化为二进制字节流（头部 JSON 元数据 + float32 连续字节），便于高效上传至对象存储。"""
    dim = len(vectors[0]) if vectors else 0
    header = json.dumps({"count": len(vectors), "dim": dim}).encode("utf-8")
    flat = array("f", [float(x) for v in vectors for x in v])
    return header + b"\n" + flat.tobytes()


def _decode_vectors(data: bytes) -> list[list[float]]:
    """从二进制字节流反序列化回原始浮点向量列表。"""
    header_raw, _, body = data.partition(b"\n")
    info = json.loads(header_raw)
    dim = int(info["dim"])
    flat = array("f")
    flat.frombytes(body)
    return [list(flat[i * dim : (i + 1) * dim]) for i in range(int(info["count"]))]


def _read_full_md(artifact: Path) -> str | None:
    """从 MinerU 返回的 ZIP 成果压缩包中读取 full.md 结构化 Markdown 文件。"""
    with zipfile.ZipFile(artifact) as bundle:
        for name in bundle.namelist():
            if name.endswith("full.md"):
                return bundle.read(name).decode("utf-8", errors="replace")
    return None


def _markdown_sections(text: str) -> tuple[Section, ...]:
    """依据 Markdown 标题层级将文本切分为结构化 Section 章节序列（完整保留 heading_path 供证据溯源）；无标题时作为单节处理。"""
    sections: list[Section] = []
    level = 1
    heading = "抽取结果"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(Section(level=level, heading=heading, text=body))

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush()
            level = len(match.group(1))
            heading = match.group(2)
            buffer = []
        else:
            buffer.append(line)
    flush()
    if not sections and text.strip():
        sections.append(Section(level=1, heading="抽取结果", text=text.strip()))
    return tuple(sections)


_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _strip_image_links(text: str) -> str:
    """剥离 markdown 中的图片语法并收敛多余空行。

    MinerU zip 内的图片链接是包内相对路径（如 ``images/xxx.jpg``），不解耦处理会成为
    分块/嵌入/索引中的垃圾 token，并可能在回答中产出死链。图片资产化（对象存储改写 +
    前端预览）依赖图片服务方案决策，落地前先剥离（ADR 0087）。
    """
    return re.sub(r"\n{3,}", "\n\n", _IMAGE_LINK_RE.sub(" ", text))


def _normalize_mineru_sections(artifact: Path) -> tuple[Section, ...]:
    """将 MinerU 解析成果归一化为标准的 Section 章节序列。

    官方返回的解析包为 ZIP 格式（包含 full.md 与结构化 JSON），按 Markdown 标题切分章节；
    非 ZIP 格式数据则一律按 UTF-8 文本作为单节内容进行安全提取。图片链接一律剥离。
    """
    with open(artifact, "rb") as handle:
        magic = handle.read(2)
    if magic == b"PK":
        markdown = _read_full_md(artifact)
        if markdown is not None:
            return _markdown_sections(_strip_image_links(markdown))
    text = artifact.read_text(encoding="utf-8", errors="replace")
    return (Section(level=1, heading="抽取结果", text=_strip_image_links(text)),)


def _to_chunk(record: ChunkRecord):
    """将持久化 ChunkRecord 转换为领域层 Chunk 实体（供 embedding_text 与 indexer 使用）。"""
    from medicalrag_core.chunking.chunking import Chunk

    return Chunk(
        document_id=record.document_id,
        text=record.text,
        heading_path=record.headings,
        index=record.index,
    )
