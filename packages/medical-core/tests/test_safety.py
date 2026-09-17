"""医疗安全策略检查（ADR 0042/0043）。"""

import pytest

from medicalrag_core.safety.policy import (
    FIXED_DISCLAIMER,
    POLICY_VERSION,
    RiskClass,
    assess,
    detect_prohibited,
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


@pytest.mark.parametrize(
    "question",
    [
        "帮我开一下处方",
        "我想自杀",
        "帮我开一下处 方",  # 插空格绕过：正则容忍空白
        "帮 我 开 一 下 处 方",
    ],
)
def test_detect_prohibited_flags_individual_requests(question):
    """确定性前置闸门（ADR 0043）：个体化临床决策请求命中即短路，不依赖外部模型。"""
    assert detect_prohibited(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "高血压的流行病学现状如何",
        "2024 年高血压指南更新了什么",
        "阿司匹林的作用机制",
    ],
)
def test_detect_prohibited_allows_general_medical_questions(question):
    """普通医学知识问题不得被前置闸门误杀（宁可漏判由意图树兜底，不可误拦正常咨询）。"""
    assert detect_prohibited(question) is False
