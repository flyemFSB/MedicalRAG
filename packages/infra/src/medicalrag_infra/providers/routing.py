"""模型路由适配器：多候选按优先级切换 + 三态熔断 + 流式首包探测。

复刻参考实现的模型容错语义（分层多候选 → 三态熔断 → 首包超时切换）：
- 候选来源为 ``model_targets`` 表中声明 ``generation`` 能力且熔断放行的目标（priority 降序），
  模型名取自目标行；base_url / api_key 复用平台级单一凭据配置（凭据多服务商存储不在 v1 范围）。
- 熔断状态（closed / open / half_open）与失败计数持久化于 model_targets 行，
  运营台「模型健康」卡片直接读取真实运行数据。
- 无任何已注册目标时回退到 Settings 提供的单一默认配置（保持既有行为）。

# ponytail: 候选为同凭据下的模型级路由；跨供应商凭据路由等 platform_credentials 支持密钥存储后再接入。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from medicalrag_core.chat.model import Analysis, ChatRequest, GenerationContext, MemoryContext
from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.intent.node import IntentNode
from medicalrag_core.model_target import CircuitState, ModelTarget
from medicalrag_infra.logging import logger
from medicalrag_infra.persistence.ops_repos import SqlModelTargetRepository
from medicalrag_infra.providers.llm import (
    LLMProviderConfig,
    OpenAICompatClassifier,
    OpenAICompatGenerator,
)

_FAILURE_THRESHOLD = 3
_COOLDOWN_S = 30.0
_FIRST_PACKET_TIMEOUT_S = 30.0


class ModelRouter:
    """候选解析与熔断状态推进（状态写回 model_targets，供健康展示与调度共同使用）。"""

    def __init__(
        self,
        repo: SqlModelTargetRepository,
        default: LLMProviderConfig,
        *,
        failure_threshold: int = _FAILURE_THRESHOLD,
        cooldown_s: float = _COOLDOWN_S,
    ) -> None:
        self._repo = repo
        self._default = default
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s

    async def candidates(self) -> list[tuple[ModelTarget, LLMProviderConfig]]:
        """按优先级返回熔断放行的生成候选；冷却到期的 OPEN 目标翻转为 HALF_OPEN 探测态。"""
        targets = list(await self._repo.list_all())
        out: list[tuple[ModelTarget, LLMProviderConfig]] = []
        now = datetime.now(UTC)
        for target in targets:
            if "generation" not in target.capabilities:
                continue
            if target.circuit is CircuitState.OPEN:
                if target.circuit_opened_at is None or now - target.circuit_opened_at < timedelta(
                    seconds=self._cooldown_s
                ):
                    continue
                target = await self._mark_half_open(target)
            out.append((target, self._config_for(target)))
        if not out:
            out.append(
                (
                    ModelTarget(
                        id="default", name="default", provider="settings", model=self._default.model
                    ),
                    self._default,
                )
            )
        return out

    def _config_for(self, target: ModelTarget) -> LLMProviderConfig:
        return LLMProviderConfig(
            base_url=self._default.base_url,
            api_key=self._default.api_key,
            model=target.model,
            timeout_s=self._default.timeout_s,
        )

    async def _mark_half_open(self, target: ModelTarget) -> ModelTarget:
        cooled = replace(target, circuit=CircuitState.HALF_OPEN)
        try:
            await self._repo.save(cooled)
        except Exception:
            logger.warning("熔断器状态切换为半开（HALF_OPEN）持久化失败：target_id={}", target.id)
        return cooled

    async def record_success(self, target: ModelTarget) -> None:
        if target.id == "default":
            return
        await self._save(
            target,
            circuit=CircuitState.CLOSED,
            failures=0,
        )

    async def record_failure(self, target: ModelTarget) -> None:
        if target.id == "default":
            return
        failures = target.failures + 1
        circuit = CircuitState.OPEN if failures >= self._failure_threshold else target.circuit
        await self._save(target, circuit=circuit, failures=failures)

    async def _save(self, target: ModelTarget, *, circuit: CircuitState, failures: int) -> None:
        opened_at = (
            datetime.now(UTC)
            if circuit is CircuitState.OPEN and target.circuit is not CircuitState.OPEN
            else target.circuit_opened_at
        )
        try:
            await self._repo.save(
                replace(target, circuit=circuit, failures=failures, circuit_opened_at=opened_at)
            )
        except Exception:
            logger.warning("模型目标熔断状态持久化失败：target_id={} circuit_state={}", target.id, circuit)


def _cached_adapter[A](
    cache: dict[str, tuple[LLMProviderConfig, A]],
    target: ModelTarget,
    config: LLMProviderConfig,
    factory: Callable[[LLMProviderConfig], A],
) -> A:
    """按目标 id 缓存适配器；运营台改 model 后配置不等即失效重建。"""
    cached = cache.get(target.id)
    if cached is None or cached[0] != config:
        adapter = factory(config)
        cache[target.id] = (config, adapter)
        return adapter
    return cached[1]


class RoutingGenerator:
    """带熔断与多候选故障转移的生成适配器（实现 Generator 协议）。"""

    def __init__(
        self,
        router: ModelRouter,
        *,
        first_packet_timeout_s: float = _FIRST_PACKET_TIMEOUT_S,
    ) -> None:
        self._router = router
        self._first_packet_timeout_s = first_packet_timeout_s
        self._adapters: dict[str, tuple[LLMProviderConfig, OpenAICompatGenerator]] = {}

    def _adapter(self, target: ModelTarget, config: LLMProviderConfig) -> OpenAICompatGenerator:
        return _cached_adapter(self._adapters, target, config, OpenAICompatGenerator)

    async def aclose(self) -> None:
        """释放缓存的全部候选适配器（组合根停机时调用）。"""
        for _, adapter in self._adapters.values():
            await adapter.aclose()
        self._adapters.clear()

    async def generate(self, context: GenerationContext) -> str:
        last: Exception | None = None
        for target, config in await self._router.candidates():
            try:
                result = await self._adapter(target, config).generate(context)
            except ProviderUnavailableError as exc:
                last = exc
                await self._router.record_failure(target)
                continue
            await self._router.record_success(target)
            return result
        raise ProviderUnavailableError(f"all_model_candidates_failed:{last}")

    async def stream(self, context: GenerationContext) -> AsyncIterator[str]:
        """流式生成（首包探测）：首个内容包未在预算内到达即切换下一候选。"""
        last: Exception | None = None
        for target, config in await self._router.candidates():
            iterator = self._adapter(target, config).stream(context).__aiter__()
            try:
                first = await asyncio.wait_for(
                    iterator.__anext__(), timeout=self._first_packet_timeout_s
                )
            except StopAsyncIteration as exc:
                # 空响应同样视为该候选失败（参考实现语义：空响应触发降级）
                last = exc
                await self._router.record_failure(target)
                continue
            except (TimeoutError, ProviderUnavailableError, asyncio.CancelledError) as exc:
                if isinstance(exc, asyncio.CancelledError):
                    # 客户端主动取消不属于模型故障：原样上抛，不计熔断
                    raise
                last = exc
                await self._router.record_failure(target)
                continue
            await self._router.record_success(target)
            yield first
            try:
                async for token in iterator:
                    yield token
            except ProviderUnavailableError as exc:
                # 首包后中途故障：记录失败并上抛，由编排层收敛为 FALLBACK
                await self._router.record_failure(target)
                raise ProviderUnavailableError(type(exc).__name__) from exc
            return
        raise ProviderUnavailableError(f"all_model_candidates_failed:{last}")


class RoutingClassifier:
    """带熔断与多候选故障转移的意图分类适配器（实现 IntentClassifier 协议）。"""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router
        self._adapters: dict[str, tuple[LLMProviderConfig, OpenAICompatClassifier]] = {}

    async def analyze(
        self,
        request: ChatRequest,
        leaves: tuple[IntentNode, ...],
        context: MemoryContext,
    ) -> Analysis:
        last: Exception | None = None
        for target, config in await self._router.candidates():
            adapter = _cached_adapter(self._adapters, target, config, OpenAICompatClassifier)
            analysis = await adapter.analyze(request, leaves, context)
            if analysis.candidates or analysis.guidance_message:
                # 分类产出可用（有候选或显式澄清）即视为成功；空候选由上层兜底澄清
                await self._router.record_success(target)
                return analysis
            last = ProviderUnavailableError("empty_classification")
            await self._router.record_failure(target)
        # 全部候选均无产出：与分类器不可用同语义（返回原问题 + 空候选 → 上层澄清）
        logger.warning("意图分类的所有候选提供商均调用失败，降级回退至空候选并触发澄清引导：error={}", last)
        return Analysis(rewritten_question=request.question, candidates=())

    async def aclose(self) -> None:
        """释放缓存的全部候选适配器（组合根停机时调用）。"""
        for _, adapter in self._adapters.values():
            await adapter.aclose()
        self._adapters.clear()
