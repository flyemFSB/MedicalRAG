"""TaskIQ 异步后台任务 Worker 组合根（遵循 version-baseline §1 门禁 3 规范：采用 TaskIQ 作为任务队列）。

核心任务：
- ``run_ingestion_stage`` —— 驱动 9 阶段文档摄取流水线（IngestionService），当前阶段完成后自动投递下一阶段任务；
  阶段幂等性由数据库唯一约束 `UNIQUE(ingestion_run_id, stage)` 兜底保障。
- ``relay_outbox`` —— 领取未处理的 Outbox 消息行并投递业务事件（SKIP LOCKED + attempts 上限）；
  单条消息投递失败仅递增 attempts 计数，超过 ``outbox_max_attempts`` 阈值的毒消息自动跳过并保持未处理状态供运维排查。

失败语义（传输层为 RabbitMQ，ADR 0086）：
- 持久化发布 + 持久化 quorum 队列：broker 重启不丢消息；消费默认 WHEN_SAVED ack，
  执行中进程崩溃的消息未确认会被 RabbitMQ 重投（at-least-once），重复执行由阶段唯一约束兜底。
- 阶段任务显式声明``retry_on_error``标签由 SmartRetryMiddleware 重试（带 delay 标签的重投
  经 taskiq.delay 延迟队列死信回主队列）；重试耗尽后由 ``IngestionFailureMiddleware``
  将 Run 置为 FAILED 终止态（运营台可见失败原因并重放）。
- 内置死信队列 taskiq.dead_letter 承接拒绝/过期/超长的消息（安全网，正常失败路径不经过）。
服务配置统一经由 pydantic-settings 在进程启动时进行校验，缺失关键配置立即触发 fail-fast 退出。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import suppress

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine
from taskiq import TaskiqEvents, TaskiqMessage, TaskiqMiddleware, TaskiqResult
from taskiq.middlewares.smart_retry_middleware import SmartRetryMiddleware
from taskiq_aio_pika import AioPikaBroker, Queue

from medicalrag_core.ingestion.state_machine import IngestionRunState
from medicalrag_infra.logging import logger
from medicalrag_infra.persistence.db import create_engine_and_session_factory
from medicalrag_infra.persistence.ingestion import SqlIngestionRunRepository
from medicalrag_infra.persistence.operator import OperatorRepositories
from medicalrag_infra.ratelimit import RedisConcurrencyGate
from medicalrag_infra.retrieval.indexer import QdrantIndexer
from medicalrag_infra.storage.local import LocalObjectStorage

from .ingestion import IngestionDeps, IngestionService


class WorkerSettings(BaseSettings):
    """Worker 运行配置项（环境变量统一使用 MEDICALRAG_ 前缀；启动时完成强类型校验，缺失必填配置则立即阻断启动）。"""

    model_config = SettingsConfigDict(env_prefix="MEDICALRAG_", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://medicalrag:medicalrag@localhost:5672/"
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
    # 僵尸 Run 自愈阈值：updated_at 停滞超过该时长（秒）的非终态 Run 置为 FAILED（可重放）
    stale_run_seconds: int = 900
    # MinerU 分布式并发闸额度：跨进程限制同时打向 MinerU 的解析任务数（保护外部服务）
    mineru_concurrency: int = 16


_settings = WorkerSettings()  # type: ignore[reportCallIssue]  # 配置通过环境变量注入；模块级单例实例


class IngestionFailureMiddleware(TaskiqMiddleware):
    """重试耗尽后将摄取 Run 置为 FAILED 终止态（状态机已定义该终态，之前无写入方）。

    与 SmartRetryMiddleware 共用同一判定（``_retries+1 >= max_retries`` 即不再重试），
    故不依赖中间件调用顺序；标记失败本身不影响原异常向 taskiq 冒泡。
    """

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[object],
        exception: BaseException,
    ) -> None:
        if message.task_name != run_ingestion_stage.task_name:
            return
        retries = int(message.labels.get("_retries", 0)) + 1
        if retries < int(message.labels.get("max_retries", 3)):
            return
        repos = _repos
        if repos is None or not message.args:
            return
        run_id = str(message.args[0])
        try:
            await repos.ingestion.mark_failed(run_id, type(exception).__name__)
            logger.error("摄取重试次数达到上限，摄取运行标记为失败（重试次数={}）：run_id={}", retries, run_id)
        except Exception:
            logger.exception("更新摄取运行失败终态时发生异常：run_id={}", run_id)


# 重投延迟队列：SmartRetryMiddleware 的重投携带 delay 标签，经本队列 TTL 过期后死信回主队列。
# 提为模块常量以便测试钉「我们自己的配置」（避免用适配器私有属性断言）。
DELAY_QUEUE = Queue(name="taskiq.delay")

broker = AioPikaBroker(
    url=_settings.rabbitmq_url,
    # prefetch：单消费者在途消息预算（官方 fair dispatch 建议；处理中的崩溃消息未 ack 会被重投）
    qos=10,
    # 任务队列/交换机/死信队列全部沿用适配器默认声明：taskiq 队列为持久化 quorum 队列，
    # 消息以 PERSISTENT 投递，taskiq.dead_letter 死信队列自动挂接。
    delay_queue=DELAY_QUEUE,
).with_middlewares(SmartRetryMiddleware(), IngestionFailureMiddleware())

# 组合根运行状态：在 Worker startup 生命周期完成装配，保持进程内单例
_service: IngestionService | None = None
_repos: OperatorRepositories | None = None
_indexer: QdrantIndexer | None = None
_relay_loop_task: asyncio.Task | None = None
_engine: AsyncEngine | None = None
_heartbeat_redis = None
_storage: LocalObjectStorage | None = None
_qdrant = None
_embedding = None
_mineru = None

_HEARTBEAT_KEY = "medicalrag:worker:heartbeat"


def _require[T](value: T | None) -> T:
    if value is None:
        raise RuntimeError("Worker 尚未完成 startup 依赖装配")
    return value


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _startup(_state) -> None:
    global _service, _repos, _indexer, _relay_loop_task, _engine, _heartbeat_redis, _storage
    global _qdrant, _embedding, _mineru
    settings = _settings
    _engine, sessions = create_engine_and_session_factory(settings.database_url)
    _repos = OperatorRepositories(sessions)
    from medicalrag_infra.providers.embeddings import OpenAICompatEmbeddingProvider
    from medicalrag_infra.providers.llm import LLMProviderConfig

    _embedding = OpenAICompatEmbeddingProvider(
        LLMProviderConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or None,
            model=settings.embedding_model,
        )
    )
    from qdrant_client import QdrantClient

    _qdrant = QdrantClient(url=settings.qdrant_url)
    _indexer = QdrantIndexer(
        _qdrant,
        _embedding,
        collection=settings.qdrant_collection,
    )
    # 启动即确保集合存在：全新部署先上传文档时，indexing/validating 不再因集合缺失而 FAILED
    from medicalrag_infra.retrieval.schema import ensure_collection

    await asyncio.to_thread(
        ensure_collection,
        _qdrant,
        settings.qdrant_collection,
        embedding_dim=settings.qdrant_embedding_dim,
    )
    _storage = LocalObjectStorage(settings.object_root)
    _mineru = _build_mineru(settings)
    # 心跳客户端：relay 循环每轮写入带 TTL 的心跳键（进程存活且循环未被卡死的可探测信号）
    from redis.asyncio import from_url

    _heartbeat_redis = from_url(settings.redis_url)
    # MinerU 分布式并发闸：复用心跳 Redis 连接，跨进程限制同时打向 MinerU 的解析任务数
    mineru_gate = (
        RedisConcurrencyGate(_heartbeat_redis, prefix="minerugate") if _mineru is not None else None
    )
    _service = IngestionService(
        IngestionDeps(
            runs=SqlIngestionRunRepository(sessions),
            documents=_repos.documents,
            storage=_storage,
            chunks=_repos.chunks,
            embeddings=_embedding,
            indexer=_indexer,
            mineru=_mineru,
            contextualizer=_build_contextualizer(settings),
            embedding_dim=settings.qdrant_embedding_dim,
            mineru_gate=mineru_gate,
            mineru_concurrency=settings.mineru_concurrency,
        )
    )
    # 启动 Outbox Relay 轮询后台协程：在事务提交后领取并投递领域事件
    _relay_loop_task = asyncio.create_task(_relay_loop())


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _shutdown(_state) -> None:
    global _relay_loop_task, _engine, _heartbeat_redis, _qdrant, _embedding, _mineru
    if _relay_loop_task is not None:
        _relay_loop_task.cancel()
        # 取消后必须 await 回收，否则可能仍在写库；CancelledError 是协程被取消的预期结果
        with suppress(asyncio.CancelledError):
            await _relay_loop_task
        _relay_loop_task = None
    # 外部客户端逐一回收（规范 §1.4：每个连接池必须有所有者与关闭路径）；单个失败不阻断其余清理
    if _mineru is not None:
        with suppress(Exception):
            await _mineru.aclose()
        _mineru = None
    if _embedding is not None:
        with suppress(Exception):
            await _embedding.aclose()
        _embedding = None
    if _qdrant is not None:
        with suppress(Exception):
            await asyncio.to_thread(_qdrant.close)
        _qdrant = None
    if _heartbeat_redis is not None:
        with suppress(Exception):
            await _heartbeat_redis.delete(_HEARTBEAT_KEY)
        await _heartbeat_redis.aclose()
        _heartbeat_redis = None
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def _relay_loop(*, interval_s: float = 5.0) -> None:
    loop_count = 0
    while True:
        try:
            await relay_outbox()
        except Exception:
            logger.exception("发件箱中继（Outbox Relay）单次轮询处理异常，将在下个周期重试")
        loop_count += 1
        # 心跳：每轮顺带刷新带 TTL 的存活信号（compose healthcheck 据此判断 worker 健康）
        if _heartbeat_redis is not None:
            with suppress(Exception):
                await _heartbeat_redis.set(_HEARTBEAT_KEY, "1", ex=45)
        # 僵尸 Run 自愈：停滞在非终态且长时间无进展的 Run 置为 FAILED（可由运营台重放续跑）
        if loop_count % 12 == 0:
            try:
                stale = await _require(_repos).ingestion.fail_stale_runs(
                    max_age_s=_settings.stale_run_seconds
                )
                if stale:
                    logger.warning("超时停滞的摄取运行已自动标记为失败终态：count={}", stale)
            except Exception:
                logger.exception("超时停滞的摄取运行清理失败，将在下个周期重试")
        await asyncio.sleep(interval_s)


def _build_mineru(settings: WorkerSettings):
    """当环境变量配置了 MEDICALRAG_MINERU_BASE_URL 时自动启用 MinerU 复杂版面解析适配器。"""
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
    """当环境变量配置了 MEDICALRAG_CONTEXT_MODEL 时自动启用文档切片背景增强补写（特性开关）。"""
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
    """执行当前摄取阶段工作并投递下一阶段异步作业。返回推进后的状态。

    PUBLISHED 虽为终态但仍需执行发布收尾（置 published / 向量检索可见资格），
    故同样投递；仅 FAILED 无后续工作。next_state == stage（PUBLISHED 阶段自返）
    时不得再投递，否则同一稳定任务 ID 会无限循环重投。
    """
    next_state = await service.run(run_id, stage)
    if next_state is not stage and next_state is not IngestionRunState.FAILED:
        await kick(run_id, next_state)
    return next_state


def _kick(run_id: str, stage: IngestionRunState) -> Coroutine:
    # 派生具有幂等稳定性的任务 ID（任务 ID 基于聚合根与阶段生成）；阶段幂等性由数据库约束兜底
    return (
        run_ingestion_stage.kicker()
        .with_task_id(f"ingest:{run_id}:{stage.value}")
        .kiq(run_id, stage)
    )


@broker.task(retry_on_error=True, max_retries=3)
async def run_ingestion_stage(run_id: str, stage: IngestionRunState) -> None:
    """推进单次文档摄取作业的指定阶段；执行成功后自动调度投递下一阶段。

    ``retry_on_error=True`` 是 SmartRetryMiddleware 生效的必要条件（其 default_retry_label 默认为
    False，裸 ``@broker.task`` 不会重试）；``max_retries`` 语义为总尝试次数。
    """
    await advance_run(_require(_service), _kick, run_id, stage)


async def relay_outbox() -> None:
    """Outbox Relay 循环体（由 ``_relay_loop`` 周期调用，不注册为 broker 任务）。

    事件类型与任务映射契约（事务性 Outbox）：
      - ``ingestion.stage`` → 推进摄取作业阶段（payload.stage）。
      - ``document.delete`` / ``document.scan_orphans`` → 动态分发到对应异步任务。

    单条事件投递失败仅记录失败次数，不阻断整批任务的投递处理；
    超过 outbox_max_attempts 最大重试上限后 claim 阶段将自动过滤跳过该消息（实施毒消息隔离，保持可见供排查）。
    投递失败已按行记录 attempts，relay 轮询下个周期自然重试。
    """
    repos = _require(_repos)
    messages = await repos.outbox.claim(100, max_attempts=_settings.outbox_max_attempts)
    for message in messages:
        try:
            if message.event_type == "ingestion.stage":
                stage = IngestionRunState(str(message.payload.get("stage", "accepted")))
                await _kick(message.aggregate_id, stage)
            else:
                # 事件名称即为注册的任务名称（如 document.delete）；scan_orphans 类为无参任务
                task = broker.find_task(message.event_type)
                if task is None:
                    raise RuntimeError(f"Outbox 事件缺失对应的已注册任务: {message.event_type}")
                args = (
                    () if message.event_type.endswith("scan_orphans") else (message.aggregate_id,)
                )
                await task.kiq(*args)
        except Exception:
            await repos.outbox.record_failure(message.id)
            # 位置参数格式化，不绑定 extra 字段（避免把事件名当成日志字段输出）
            logger.error(
                "发件箱事件消息投递失败（当前重试次数={}，最大重试上限={}）：event_type={}",
                message.attempts + 1,
                _settings.outbox_max_attempts,
                message.event_type,
            )
            continue
        await repos.outbox.mark_processed(message.id)


@broker.task(task_name="document.unpublish")
async def unpublish_document(document_id: str) -> None:
    """下架文档：先切换 Qdrant 索引中的向量点可见性（检索仅过滤索引属性），再更新 PostgreSQL 中的状态标记。"""
    indexer = _require(_indexer)
    repos = _require(_repos)
    await indexer.set_eligibility(document_id, False)
    await repos.documents.set_published(document_id, False)


@broker.task(task_name="document.publish")
async def republish_document(document_id: str) -> None:
    """重新发布文档：恢复文档在关系库与向量索引中的检索可见资格。"""
    indexer = _require(_indexer)
    repos = _require(_repos)
    await repos.documents.set_published(document_id, True)
    await indexer.set_eligibility(document_id, True)


@broker.task(task_name="document.delete")
async def delete_document_points(document_id: str) -> None:
    """级联物理删除文档：先清理 Qdrant 索引中的向量点，确认清空后再删除 PostgreSQL 实体行（向量先行，最小化脏读窗口）。"""
    indexer = _require(_indexer)
    repos = _require(_repos)
    await indexer.delete_document(document_id)
    await repos.documents.delete(document_id)
    logger.info("文档级联物理删除完成：document_id={}", document_id)


@broker.task(task_name="document.scan_orphans")
async def scan_orphan_chunks() -> int:
    """孤儿分块对账与清理任务：对比向量索引与关系库，自动清理 document_id 已在关系库中被删除的残留向量点。"""
    indexer = _require(_indexer)
    known = set(await _require(_repos).documents.list_ids())
    indexed = await indexer.all_document_ids()
    orphans = indexed - known
    for document_id in sorted(orphans):
        await indexer.delete_document(document_id)
    logger.info(
        "孤儿分块对账扫描与清理完成：有效文档 {} 篇，清理残留孤儿分块所属文档 {} 篇",
        len(known),
        len(orphans),
    )
    return len(orphans)


@broker.task(task_name="objects.scan_orphans")
async def scan_orphan_objects() -> int:
    """孤儿对象对账与清理任务：删除对象存储中不再被任何 Run 元数据引用的存储对象。

    引用集 = 全部 Run 元数据中的 object_key / artifact_ref / vectors_ref；
    1 小时新近度保护规避"上传已落盘但 Run 元数据尚未提交"的竞态窗口。
    """
    storage = _require(_storage)
    metas = await _require(_repos).ingestion.all_metadata()
    referenced: set[str] = set()
    for meta in metas:
        for key in ("object_key", "artifact_ref", "vectors_ref"):
            value = meta.get(key)
            if value:
                referenced.add(str(value))
    removed = await storage.scan_orphans(referenced, min_age_s=3600)
    logger.info(
        "孤儿存储对象对账与清理完成：有效引用对象 {} 个，清理失效孤儿对象 {} 个", len(referenced), removed
    )
    return removed
