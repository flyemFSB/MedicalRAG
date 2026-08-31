"""TaskIQ 异步后台任务 Worker 组合根（遵循 version-baseline §1 门禁 3 规范：采用 TaskIQ 作为任务队列，ADR 0073）。

核心任务：
- ``run_ingestion_stage`` —— 驱动 9 阶段文档摄取流水线（IngestionService），当前阶段完成后自动投递下一阶段任务；
  阶段幂等性由数据库唯一约束 `UNIQUE(ingestion_run_id, stage)` 兜底保障（ADR 0063）。
- ``relay_outbox`` —— 采用 SKIP LOCKED 避免并发竞争领取未处理的 Outbox 消息行，投递业务事件并标记已处理；
  单条消息投递失败仅递增 attempts 计数，超过 ``outbox_max_attempts`` 阈值的毒消息将自动跳过并保持未处理状态供运维排查（ADR 0080）。

任务失败重试机制：通过 Worker 重试中间件与标签进行控制；重试次数耗尽后作业状态置为 FAILED（供运营控制台查看失败原因与发起手动重放）。
服务配置统一经由 pydantic-settings 在进程启动时进行校验，缺失关键配置立即触发 fail-fast 退出。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

from pydantic_settings import BaseSettings, SettingsConfigDict
from taskiq.events import TaskiqEvents
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from medicalrag_core.ingestion.state_machine import IngestionRunState, is_terminal
from medicalrag_infra.logging import logger
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.ingestion import SqlIngestionRunRepository
from medicalrag_infra.persistence.operator import OperatorRepositories
from medicalrag_infra.retrieval.indexer import QdrantIndexer
from medicalrag_infra.storage.local import LocalObjectStorage

from .ingestion import IngestionDeps, IngestionService


class WorkerSettings(BaseSettings):
    """Worker 运行配置项（环境变量统一使用 MEDICALRAG_ 前缀；启动时完成强类型校验，缺失必填配置则立即阻断启动）。"""

    model_config = SettingsConfigDict(env_prefix="MEDICALRAG_", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "medical_chunks_v1"
    qdrant_embedding_dim: int = 1536
    llm_base_url: str = "https://api.openai.com"
    llm_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    mineru_base_url: str = ""
    mineru_token: str = ""
    context_model: str = ""
    object_root: str = "./objects"
    outbox_max_attempts: int = 5


_settings = WorkerSettings()  # type: ignore[reportCallIssue]  # 配置通过环境变量注入；模块级单例实例
_redis_url = _settings.redis_url
# redis-py 8 默认包含 socket_timeout=5s 设置，会意外打断 ListQueueBroker 的阻塞式 brpop 队列监听
# （遵循 version-baseline §1 门禁 3）；显式关闭读取超时以恢复队列消费者的标准语义
broker = ListQueueBroker(url=_redis_url, socket_timeout=None).with_result_backend(
    RedisAsyncResultBackend(redis_url=_redis_url, keep_results=False)
)

# 组合根运行状态：在 Worker startup 生命周期完成装配，保持进程内单例
_service: IngestionService | None = None
_repos: OperatorRepositories | None = None
_indexer: QdrantIndexer | None = None
_relay_loop_task: asyncio.Task | None = None


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _startup(_state) -> None:
    global _service, _repos, _indexer, _relay_loop_task
    settings = _settings
    _engine, sessions = create_engine_and_session_factory(settings.database_url)
    _repos = OperatorRepositories(sessions)
    embedding_provider = await _build_embedding_provider(settings)
    _indexer = QdrantIndexer(
        await _build_qdrant(settings),
        embedding_provider,
        collection=settings.qdrant_collection,
    )
    _service = IngestionService(
        IngestionDeps(
            runs=SqlIngestionRunRepository(sessions),
            documents=_repos.documents,
            storage=LocalObjectStorage(settings.object_root),
            chunks=_repos.chunks,
            embeddings=embedding_provider,
            indexer=_indexer,
            mineru=_build_mineru(settings),
            contextualizer=_build_contextualizer(settings),
            embedding_dim=settings.qdrant_embedding_dim,
        )
    )
    # 启动 Outbox Relay 轮询后台协程：在事务提交后领取并投递领域事件（ADR 0063）
    _relay_loop_task = asyncio.create_task(_relay_loop())


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _shutdown(_state) -> None:
    global _relay_loop_task
    if _relay_loop_task is not None:
        _relay_loop_task.cancel()
        _relay_loop_task = None


async def _relay_loop(*, interval_s: float = 5.0) -> None:
    while True:
        try:
            await relay_outbox()
        except Exception:  # noqa: BLE001 —— Relay 循环具备自愈能力，单次异常不影响后续轮询
            logger.exception("Outbox Relay 单次轮询发生异常，将在下个周期重试")
        await asyncio.sleep(interval_s)


async def _build_embedding_provider(settings: WorkerSettings):
    from medicalrag_infra.providers.embeddings import OpenAICompatEmbeddingProvider
    from medicalrag_infra.providers.llm import LLMProviderConfig

    return OpenAICompatEmbeddingProvider(
        LLMProviderConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or None,
            model=settings.embedding_model,
        )
    )


async def _build_qdrant(settings: WorkerSettings):
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url)


def _build_mineru(settings: WorkerSettings):
    """当环境变量配置了 MEDICALRAG_MINERU_BASE_URL 时自动启用 MinerU 复杂版面解析适配器（ADR 0014 / ADR 0015）。"""
    from medicalrag_infra.providers.mineru import MinerUClient, MinerUConfig

    if not settings.mineru_base_url:
        return None
    return MinerUClient(
        MinerUConfig(
            base_url=settings.mineru_base_url,
            token=settings.mineru_token or None,
        )
    )


def _build_contextualizer(settings: WorkerSettings):
    """当环境变量配置了 MEDICALRAG_CONTEXT_MODEL 时自动启用文档切片背景增强补写（ADR 0078 特性开关）。"""
    from medicalrag_infra.providers.llm import LLMProviderConfig, OpenAICompatContextualizer

    if not settings.context_model:
        return None
    return OpenAICompatContextualizer(
        LLMProviderConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or None,
            model=settings.context_model,
        )
    )


async def advance_run(
    service: IngestionService,
    kick: Callable[[str, IngestionRunState], Coroutine],
    run_id: str,
    stage: IngestionRunState,
) -> IngestionRunState:
    """执行当前摄取阶段工作并投递下一阶段异步作业；若进入终止状态则停止继续投递。返回推进后的状态。"""
    next_state = await service.run(run_id, stage)
    if not is_terminal(next_state):
        await kick(run_id, next_state)
    return next_state


def _kick(run_id: str, stage: IngestionRunState) -> Coroutine:
    # 派生具有幂等稳定性的任务 ID（ADR 0066：任务 ID 基于聚合根与阶段生成）；阶段幂等性由数据库约束兜底
    return (
        run_ingestion_stage.kicker()
        .with_task_id(f"ingest:{run_id}:{stage.value}")
        .kiq(run_id, stage)
    )


@broker.task
async def run_ingestion_stage(run_id: str, stage: IngestionRunState) -> None:
    """推进单次文档摄取作业的指定阶段；执行成功后自动调度投递下一阶段。"""
    if _service is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    await advance_run(_service, _kick, run_id, stage)


@broker.task
async def relay_outbox() -> None:
    """Outbox Relay 任务：领取未处理的事务性事件并分发投递；成功投递后打标已处理时间戳。

    事件类型与任务映射契约（ADR 0063 事务性 Outbox）：
      - ``ingestion.stage`` → 推进摄取作业阶段（payload.stage）。
      - ``document.delete`` / ``document.scan_orphans`` → 动态分发到对应的异步任务。

    单条事件投递失败仅记录失败次数，不阻断整批任务的投递处理；
    超过 outbox_max_attempts 最大重试上限后 claim 阶段将自动过滤跳过该消息（实施毒消息隔离，保持可见供排查，ADR 0080）。
    """
    if _repos is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    messages = await _repos.outbox.claim(100, max_attempts=_settings.outbox_max_attempts)
    for message in messages:
        try:
            if message.event_type == "ingestion.stage":
                stage = IngestionRunState(str(message.payload.get("stage", "accepted")))
                await _kick(message.aggregate_id, stage)
            else:
                # 事件名称即为注册的任务名称（如 document.delete / document.scan_orphans）
                task = broker.find_task(message.event_type)
                if task is None:
                    raise RuntimeError(f"Outbox 事件缺失对应的已注册任务: {message.event_type}")
                await task.kiq(message.aggregate_id)
        except Exception:  # noqa: BLE001 —— 单条失败递增计数后继续处理后续消息，避免整批阻塞
            await _repos.outbox.record_failure(message.id)
            logger.error(
                "Outbox 消息投递失败（当前重试次数={attempts}，重试上限={cap}）：event={event}",
                attempts=message.attempts + 1,
                cap=_settings.outbox_max_attempts,
                event=message.event_type,
            )
            continue
        await _repos.outbox.mark_processed(message.id)


@broker.task(task_name="document.unpublish")
async def unpublish_document(document_id: str) -> None:
    """下架文档（ADR 0079）：先切换 Qdrant 索引中的向量点可见性（检索仅过滤索引属性），再更新 PostgreSQL 中的状态标记。"""
    if _indexer is None or _repos is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    await _indexer.set_eligibility(document_id, False)
    await _repos.documents.set_published(document_id, False)


@broker.task(task_name="document.publish")
async def republish_document(document_id: str) -> None:
    """重新发布文档（ADR 0079）：恢复文档在关系库与向量索引中的检索可见资格。"""
    if _indexer is None or _repos is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    await _repos.documents.set_published(document_id, True)
    await _indexer.set_eligibility(document_id, True)


@broker.task(task_name="document.delete")
async def delete_document_points(document_id: str) -> None:
    """级联物理删除文档（ADR 0079）：先清理 Qdrant 索引中的向量点，确认清空后再删除 PostgreSQL 实体行（向量先行，最小化脏读窗口）。"""
    if _indexer is None or _repos is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    await _indexer.delete_document(document_id)
    await _repos.documents.delete(document_id)
    logger.info("文档级联删除完成: {}", document_id)


@broker.task(task_name="document.scan_orphans")
async def scan_orphan_chunks() -> int:
    """孤儿切片对账与清理任务（ADR 0079）：对比向量索引与关系库，自动清理 document_id 已在关系库中被删除的残留向量点。"""
    if _indexer is None or _repos is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    known = set(await _repos.documents.list_ids())
    indexed = await _indexer.all_document_ids()
    orphans = indexed - known
    for document_id in sorted(orphans):
        await _indexer.delete_document(document_id)
    logger.info(
        "孤儿切片扫描与对账清理完成: 存在有效文档 {} 篇 / 清理孤儿切片所属文档 {} 篇",
        len(known),
        len(orphans),
    )
    return len(orphans)
