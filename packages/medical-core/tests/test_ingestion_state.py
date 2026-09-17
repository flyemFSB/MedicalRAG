"""Ingestion Run 状态机检查（九阶段只前向，ADR 0013/0063）。"""

import pytest

from medicalrag_core.ingestion.state_machine import (
    IngestionRunState,
    InvalidIngestionTransition,
    advance,
    is_terminal,
    precedes,
)


def test_forward_progression_through_all_nine_stages():
    state = IngestionRunState.ACCEPTED
    expected = [
        IngestionRunState.EXTRACTING,
        IngestionRunState.EXTRACTED,
        IngestionRunState.CHUNKING,
        IngestionRunState.ENRICHING,
        IngestionRunState.EMBEDDING,
        IngestionRunState.INDEXING,
        IngestionRunState.VALIDATING,
        IngestionRunState.PUBLISHED,
    ]
    for target in expected:
        state = advance(state)
        assert state is target
    assert is_terminal(state)


def test_published_is_terminal_and_cannot_advance():
    with pytest.raises(InvalidIngestionTransition):
        advance(IngestionRunState.PUBLISHED)


def test_failed_is_terminal_and_cannot_advance():
    assert is_terminal(IngestionRunState.FAILED)
    with pytest.raises(InvalidIngestionTransition):
        advance(IngestionRunState.FAILED)


def test_non_terminal_stages_can_advance():
    assert not is_terminal(IngestionRunState.ACCEPTED)
    assert not is_terminal(IngestionRunState.VALIDATING)


def test_precedes_orders_stages_and_rejects_backwards():
    """at-least-once 重复投递：滞后阶段的任务必须能被识别为幂等成功，而非当作阶段错位。"""
    assert precedes(IngestionRunState.ACCEPTED, IngestionRunState.EXTRACTING)
    assert not precedes(IngestionRunState.EXTRACTING, IngestionRunState.ACCEPTED)
    # 同一阶段既非前趋也非后继（重复投递同一阶段不应误判为滞后）
    assert not precedes(IngestionRunState.CHUNKING, IngestionRunState.CHUNKING)
