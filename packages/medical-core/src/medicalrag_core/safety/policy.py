"""医疗安全边界策略定义。

安全分类为检索前强制执行的确定性策略阶段，不依赖外部模型的可用性。
意图节点通过 ``safety_class`` 声明医疗风险等级；
对于 PROHIBITED（个体化临床决策）请求，系统在检索前立即短路拦截，并返回固定的免责声明与就医引导语，
坚决杜绝将一般性医学证据拼装为个体化临床诊疗方案。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# 固定免责声明（版本化产品文案，不由模型生成，不随单次响应动态变化）。
FIXED_DISCLAIMER = "AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准"

# 安全策略版本号：策略规则调整时递增，写入 Run 事件日志供审计追踪与评测对齐。
POLICY_VERSION = 1


class RiskClass(enum.StrEnum):
    """意图触达时的医疗安全风险等级枚举。"""

    GENERAL = "general"  # 一般医学普及知识：执行正常证据检索流水线 + 基线免责声明
    TREATMENT = "treatment"  # 治疗或用药咨询：执行证据检索流水线 + 适用范围提示 + 就医引导语
    URGENT = "urgent"  # 急症与危重症状咨询：执行证据检索流水线 + 紧急就医提示 + 急救引导语
    PROHIBITED = "prohibited"  # 个体化临床决策：检索前直接短路拦截


@dataclass(frozen=True, slots=True)
class SafetyAssessment:
    """单次安全评估输出：包含风险等级、是否短路、范围提示、就医引导语与策略版本。"""

    risk_class: RiskClass
    prohibited: bool
    scope_notice: str | None
    escalation: str | None
    policy_version: int

    def to_payload(self) -> dict[str, object]:
        """安全评估的对外数据载荷（SSE 端点与 Agent Graph 共享统一出口）。"""
        return {
            "risk_class": self.risk_class.value,
            "scope_notice": self.scope_notice,
            "escalation": self.escalation,
        }


# 范围提示与升级用语为预设产品文案（可随设计规范微调）；免责声明除外（固定文本）。
_NOTICE: dict[RiskClass, str] = {
    RiskClass.TREATMENT: "回答仅提供一般医学知识，不构成个体化治疗方案；请以医嘱为准。",
    RiskClass.URGENT: "回答仅提供一般医学知识，不替代急诊评估；紧急情况请立即就医。",
}
_ESCALATION: dict[RiskClass, str] = {
    RiskClass.TREATMENT: "如涉及您个人的治疗决策，请咨询执业医生。",
    RiskClass.URGENT: "如出现急症，请立即拨打急救电话或前往急诊。",
    RiskClass.PROHIBITED: "该请求涉及个体化诊疗决策，AI 无法提供；请及时咨询执业医生。",
}


def assess(risk_class: RiskClass) -> SafetyAssessment:
    """根据风险等级执行安全评估；PROHIBITED 等级触发检索前短路拦截。"""
    return SafetyAssessment(
        risk_class=risk_class,
        prohibited=risk_class is RiskClass.PROHIBITED,
        scope_notice=_NOTICE.get(risk_class),
        escalation=_ESCALATION.get(risk_class),
        policy_version=POLICY_VERSION,
    )


def short_circuit_message(assessment: SafetyAssessment) -> str:
    """生成 PROHIBITED 短路分支的固定安全引导响应：就医引导语 + 免责声明。"""
    if not assessment.prohibited:
        raise ValueError("仅 PROHIBITED 评估可生成短路响应")
    return f"{_ESCALATION[RiskClass.PROHIBITED]}\n{FIXED_DISCLAIMER}"
