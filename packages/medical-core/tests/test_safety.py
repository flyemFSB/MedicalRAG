"""医疗安全策略检查（ADR 0042/0043）。"""

import pytest

from medicalrag_core.safety.policy import (
    FIXED_DISCLAIMER,
    POLICY_VERSION,
    RiskClass,
    assess,
    short_circuit_message,
)


def test_fixed_disclaimer_text_is_versioned_product_copy():
    assert FIXED_DISCLAIMER == "AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准"


def test_general_has_baseline_only():
    assessment = assess(RiskClass.GENERAL)
    assert not assessment.prohibited
    assert assessment.scope_notice is None
    assert assessment.escalation is None
    assert assessment.policy_version == POLICY_VERSION


def test_treatment_has_scope_notice_and_escalation():
    assessment = assess(RiskClass.TREATMENT)
    assert not assessment.prohibited
    assert assessment.scope_notice
    assert assessment.escalation


def test_urgent_has_scope_notice_and_escalation():
    assessment = assess(RiskClass.URGENT)
    assert not assessment.prohibited
    assert assessment.scope_notice
    assert assessment.escalation


def test_prohibited_short_circuits_with_disclaimer():
    assessment = assess(RiskClass.PROHIBITED)
    assert assessment.prohibited
    message = short_circuit_message(assessment)
    assert FIXED_DISCLAIMER in message
    assert assessment.escalation in message


def test_short_circuit_message_rejects_non_prohibited():
    with pytest.raises(ValueError):
        short_circuit_message(assess(RiskClass.GENERAL))
