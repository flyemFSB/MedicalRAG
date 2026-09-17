"""ModelRouter 三态熔断与候选解析（providers/routing.py 接缝）。

接缝：`ModelRouter.candidates/record_success/record_failure`。
用内存 fake repo，不碰真实 HTTP/DB；只钉状态机可观察行为。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medicalrag_core.model_target import CircuitState, ModelTarget
from medicalrag_infra.providers.llm import LLMProviderConfig
from medicalrag_infra.providers.routing import ModelRouter

DEFAULT = LLMProviderConfig(base_url="https://llm.example", api_key="k", model="gpt-4o-mini")


class FakeTargetRepo:
    def __init__(self, targets: list[ModelTarget] | None = None) -> None:
        self.targets = {t.id: t for t in (targets or [])}
        self.saved: list[ModelTarget] = []

    async def list_all(self) -> tuple[ModelTarget, ...]:
        return tuple(self.targets.values())

    async def save(self, target: ModelTarget) -> None:
        self.saved.append(target)
        self.targets[target.id] = target


def _target(
    id: str = "t1",
    *,
    circuit: CircuitState = CircuitState.CLOSED,
    failures: int = 0,
    capabilities: frozenset[str] = frozenset({"generation"}),
    circuit_opened_at: datetime | None = None,
    model: str = "model-a",
    priority: int = 10,
) -> ModelTarget:
    return ModelTarget(
        id=id,
        name=id,
        provider="openai",
        model=model,
        capabilities=capabilities,
        priority=priority,
        circuit=circuit,
        failures=failures,
        circuit_opened_at=circuit_opened_at,
    )


async def test_no_registered_targets_falls_back_to_settings_default():
    router = ModelRouter(FakeTargetRepo(), DEFAULT, failure_threshold=3, cooldown_s=30)
    candidates = await router.candidates()
    assert len(candidates) == 1
    assert candidates[0][0].id == "default"
    assert candidates[0][1] is DEFAULT


async def test_non_generation_capability_is_excluded():
    repo = FakeTargetRepo(
        [_target(capabilities=frozenset({"dense"}), model="embed-only")],
    )
    router = ModelRouter(repo, DEFAULT)
    candidates = await router.candidates()
    assert [t.id for t, _ in candidates] == ["default"]


async def test_open_circuit_within_cooldown_is_not_a_candidate():
    opened = datetime.now(UTC) - timedelta(seconds=5)
    repo = FakeTargetRepo([_target(circuit=CircuitState.OPEN, circuit_opened_at=opened)])
    router = ModelRouter(repo, DEFAULT, failure_threshold=3, cooldown_s=30)
    candidates = await router.candidates()
    assert [t.id for t, _ in candidates] == ["default"]


async def test_open_circuit_after_cooldown_flips_half_open_and_is_included():
    opened = datetime.now(UTC) - timedelta(seconds=60)
    repo = FakeTargetRepo(
        [_target(circuit=CircuitState.OPEN, circuit_opened_at=opened, model="model-a")]
    )
    router = ModelRouter(repo, DEFAULT, failure_threshold=3, cooldown_s=30)
    candidates = await router.candidates()
    assert [t.id for t, _ in candidates] == ["t1"]
    assert candidates[0][0].circuit is CircuitState.HALF_OPEN
    assert candidates[0][1].model == "model-a"
    assert repo.saved[-1].circuit is CircuitState.HALF_OPEN


async def test_record_failure_opens_circuit_at_threshold():
    repo = FakeTargetRepo([_target(failures=2)])  # threshold=3，再失败一次即 open
    router = ModelRouter(repo, DEFAULT, failure_threshold=3, cooldown_s=30)
    target = repo.targets["t1"]
    await router.record_failure(target)
    saved = repo.saved[-1]
    assert saved.failures == 3
    assert saved.circuit is CircuitState.OPEN
    assert saved.circuit_opened_at is not None


async def test_record_failure_below_threshold_keeps_closed():
    repo = FakeTargetRepo([_target(failures=0)])
    router = ModelRouter(repo, DEFAULT, failure_threshold=3, cooldown_s=30)
    await router.record_failure(repo.targets["t1"])
    saved = repo.saved[-1]
    assert saved.failures == 1
    assert saved.circuit is CircuitState.CLOSED


async def test_record_success_closes_and_resets_failures():
    opened = datetime.now(UTC) - timedelta(seconds=1)
    repo = FakeTargetRepo(
        [
            _target(
                circuit=CircuitState.HALF_OPEN,
                failures=2,
                circuit_opened_at=opened,
            )
        ]
    )
    router = ModelRouter(repo, DEFAULT)
    await router.record_success(repo.targets["t1"])
    saved = repo.saved[-1]
    assert saved.circuit is CircuitState.CLOSED
    assert saved.failures == 0


async def test_default_target_skips_circuit_persistence():
    """无注册目标时的 settings 兜底不可写库（id=default 非真实行）。"""
    repo = FakeTargetRepo([])
    router = ModelRouter(repo, DEFAULT)
    default_target = ModelTarget(id="default", name="default", provider="settings", model="m")
    await router.record_failure(default_target)
    await router.record_success(default_target)
    assert repo.saved == []


async def test_candidates_use_priority_order_from_repo():
    # FakeTargetRepo 不排序；真实仓储 order_by priority desc。这里只钉「透传顺序」契约。
    low = _target(id="low", priority=1, model="m-low")
    high = _target(id="high", priority=9, model="m-high")
    repo = FakeTargetRepo([high, low])
    router = ModelRouter(repo, DEFAULT)
    candidates = await router.candidates()
    assert [t.id for t, _ in candidates] == ["high", "low"]


# --- RoutingGenerator 故障转移（接缝：generate/stream 的候选切换） ---


def _context():
    from medicalrag_core.chat.model import GenerationContext, MemoryContext

    return GenerationContext(
        question="q",
        rewritten_question="q",
        evidence=(),
        memory=MemoryContext(),
    )


class _FakeAdapter:
    def __init__(self, *, text: str | None = None, fail: bool = False, empty_stream: bool = False):
        self._text = text
        self._fail = fail
        self._empty_stream = empty_stream

    async def generate(self, _ctx):
        if self._fail:
            from medicalrag_core.chat.ports import ProviderUnavailableError

            raise ProviderUnavailableError("down")
        return self._text or "ok"

    async def stream(self, _ctx):
        if self._empty_stream:
            return
            yield  # pragma: no cover
        if self._fail:
            from medicalrag_core.chat.ports import ProviderUnavailableError

            raise ProviderUnavailableError("down")
        yield "tok"

    async def aclose(self) -> None:
        pass


async def test_generate_fails_over_to_next_candidate(monkeypatch):
    from medicalrag_infra.providers.routing import RoutingGenerator

    by_model = {
        "m-bad": _FakeAdapter(fail=True),
        "m-good": _FakeAdapter(text="from-good"),
    }

    class _Gen:
        def __init__(self, config):
            self._adapter = by_model[config.model]

        async def generate(self, ctx):
            return await self._adapter.generate(ctx)

        async def aclose(self):
            pass

    monkeypatch.setattr("medicalrag_infra.providers.routing.OpenAICompatGenerator", _Gen)
    repo = FakeTargetRepo([_target(id="bad", model="m-bad"), _target(id="good", model="m-good")])
    # list_all 透传顺序；candidates 不重排
    gen = RoutingGenerator(ModelRouter(repo, DEFAULT))
    assert await gen.generate(_context()) == "from-good"
    assert repo.targets["bad"].failures == 1
    assert repo.targets["good"].failures == 0


async def test_generate_all_candidates_failed_raises(monkeypatch):
    from medicalrag_core.chat.ports import ProviderUnavailableError
    from medicalrag_infra.providers.routing import RoutingGenerator

    class _Gen:
        def __init__(self, config):
            pass

        async def generate(self, ctx):
            raise ProviderUnavailableError("down")

        async def aclose(self):
            pass

    monkeypatch.setattr("medicalrag_infra.providers.routing.OpenAICompatGenerator", _Gen)
    repo = FakeTargetRepo([_target(id="only", model="m-x")])
    gen = RoutingGenerator(ModelRouter(repo, DEFAULT, failure_threshold=9))
    with pytest.raises(ProviderUnavailableError, match="all_model_candidates_failed"):
        await gen.generate(_context())


async def test_stream_empty_first_response_fails_over(monkeypatch):
    from medicalrag_infra.providers.routing import RoutingGenerator

    by_model = {
        "m-empty": _FakeAdapter(empty_stream=True),
        "m-good": _FakeAdapter(text="tok"),
    }

    class _Gen:
        def __init__(self, config):
            self._adapter = by_model[config.model]

        def stream(self, ctx):
            return self._adapter.stream(ctx)

        async def aclose(self):
            pass

    monkeypatch.setattr("medicalrag_infra.providers.routing.OpenAICompatGenerator", _Gen)
    repo = FakeTargetRepo([_target(id="e", model="m-empty"), _target(id="g", model="m-good")])
    gen = RoutingGenerator(ModelRouter(repo, DEFAULT))
    tokens = [t async for t in gen.stream(_context())]
    assert tokens == ["tok"]
