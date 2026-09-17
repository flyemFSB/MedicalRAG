"""模型目标与熔断状态语义检查（spec 用户故事 26/27；CONTEXT：Model Target）。"""

from medicalrag_core.model_target import CircuitState, ModelTarget


def test_circuit_allows_closed_and_half_open():
    closed = ModelTarget(
        id="t1",
        name="gpt",
        provider="openai",
        model="gpt-4o-mini",
        circuit=CircuitState.CLOSED,
    )
    half = ModelTarget(
        id="t2",
        name="gpt",
        provider="openai",
        model="gpt-4o-mini",
        circuit=CircuitState.HALF_OPEN,
    )
    open_ = ModelTarget(
        id="t3",
        name="gpt",
        provider="openai",
        model="gpt-4o-mini",
        circuit=CircuitState.OPEN,
    )
    assert closed.circuit_allows
    assert half.circuit_allows
    assert not open_.circuit_allows
