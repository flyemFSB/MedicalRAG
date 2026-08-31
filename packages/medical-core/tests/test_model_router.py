"""模型路由与三态熔断检查（spec 用户故事 26/27；CONTEXT：Model Target）。"""

from medicalrag_core.model_router.model import (
    CircuitPolicy,
    CircuitState,
    next_state,
)


def test_closed_failures_advance_to_open_at_threshold():
    policy = CircuitPolicy(failure_threshold=3)
    state, failures = CircuitState.CLOSED, 0
    for _ in range(2):
        state, failures = next_state(state, success=False, failures=failures, policy=policy)
        assert state is CircuitState.CLOSED
    state, failures = next_state(state, success=False, failures=failures, policy=policy)
    assert state is CircuitState.OPEN
    assert failures == 0


def test_closed_success_resets_failures():
    policy = CircuitPolicy(failure_threshold=3)
    _, failures = next_state(CircuitState.CLOSED, success=False, failures=1, policy=policy)
    assert failures == 2
    state, failures = next_state(
        CircuitState.CLOSED, success=True, failures=failures, policy=policy
    )
    assert state is CircuitState.CLOSED
    assert failures == 0


def test_half_open_success_closes_failure_reopens():
    policy = CircuitPolicy()
    state, _ = next_state(CircuitState.HALF_OPEN, success=True, failures=0, policy=policy)
    assert state is CircuitState.CLOSED
    state, _ = next_state(CircuitState.HALF_OPEN, success=False, failures=0, policy=policy)
    assert state is CircuitState.OPEN
