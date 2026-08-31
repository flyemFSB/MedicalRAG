"""聊天 Run 状态机检查（architecture.md「Chat State Machine」）。"""

from medicalrag_core.chat.run_state import (
    ChatRunEvent,
    ChatRunState,
    InvalidChatRunTransition,
    is_terminal,
    transition,
)


def test_normal_grounded_path_reaches_completed():
    state = ChatRunState.ACCEPTED
    state = transition(state, ChatRunEvent.MEMORY_LOADED)
    state = transition(state, ChatRunEvent.ANALYZED)
    state = transition(state, ChatRunEvent.ROUTE_RETRIEVAL)
    state = transition(state, ChatRunEvent.EVIDENCE_FOUND)
    state = transition(state, ChatRunEvent.MODEL_COMPLETED)
    assert state is ChatRunState.COMPLETED
    assert is_terminal(state)


def test_short_circuit_outcomes_converge_on_completed():
    for branch in (
        (ChatRunEvent.ROUTE_GUIDANCE, ChatRunState.GUIDANCE),
        (ChatRunEvent.ROUTE_SYSTEM_ONLY, ChatRunState.SYSTEM_ONLY),
    ):
        state = transition(ChatRunState.MEMORY_LOADED, ChatRunEvent.ANALYZED)
        state = transition(state, branch[0])
        assert state is branch[1]
        assert transition(state, ChatRunEvent.COMPLETE) is ChatRunState.COMPLETED


def test_safety_short_circuit_converges_on_completed():
    # ADR 0043：PROHIBITED 个体化临床决策在检索前短路（SAFETY 状态为计划扩展）。
    state = transition(ChatRunState.ANALYZED, ChatRunEvent.ROUTE_SAFETY)
    assert state is ChatRunState.SAFETY
    assert transition(state, ChatRunEvent.COMPLETE) is ChatRunState.COMPLETED
    assert not is_terminal(ChatRunState.SAFETY)


def test_empty_and_fallback_outcomes_converge_on_completed():
    state = transition(ChatRunState.ANALYZED, ChatRunEvent.ROUTE_RETRIEVAL)
    state = transition(state, ChatRunEvent.NO_EVIDENCE)
    assert state is ChatRunState.EMPTY
    assert transition(state, ChatRunEvent.COMPLETE) is ChatRunState.COMPLETED

    state = transition(ChatRunState.ANALYZED, ChatRunEvent.ROUTE_RETRIEVAL)
    state = transition(state, ChatRunEvent.EVIDENCE_FOUND)
    state = transition(state, ChatRunEvent.PROVIDER_FAILURE)
    assert state is ChatRunState.FALLBACK
    assert transition(state, ChatRunEvent.COMPLETE) is ChatRunState.COMPLETED


def test_failed_only_from_accepted():
    assert transition(ChatRunState.ACCEPTED, ChatRunEvent.FAILED) is ChatRunState.FAILED
    assert is_terminal(ChatRunState.FAILED)


def test_cancelled_from_memory_loaded_and_generating():
    assert transition(ChatRunState.MEMORY_LOADED, ChatRunEvent.CANCELLED) is ChatRunState.CANCELLED
    assert transition(ChatRunState.GENERATING, ChatRunEvent.CANCELLED) is ChatRunState.CANCELLED
    assert is_terminal(ChatRunState.CANCELLED)


def test_undefined_transition_raises():
    for state, event in (
        (ChatRunState.ACCEPTED, ChatRunEvent.CANCELLED),
        (ChatRunState.ANALYZED, ChatRunEvent.MODEL_COMPLETED),
        (ChatRunState.COMPLETED, ChatRunEvent.MODEL_COMPLETED),
    ):
        try:
            transition(state, event)
        except InvalidChatRunTransition as exc:
            assert exc.args[0] is state
        else:
            raise AssertionError(f"expected InvalidChatRunTransition for {state} + {event}")


def test_terminal_states_are_only_completed_failed_cancelled():
    assert is_terminal(ChatRunState.COMPLETED)
    assert is_terminal(ChatRunState.FAILED)
    assert is_terminal(ChatRunState.CANCELLED)
    assert not is_terminal(ChatRunState.ANALYZED)
    assert not is_terminal(ChatRunState.GENERATING)
