"""医疗安全边界策略定义。

安全分类为检索前强制执行的确定性策略阶段，不依赖外部模型的可用性。
意图节点通过 ``safety_class`` 声明医疗风险等级；
对于 PROHIBITED（个体化临床决策）请求，系统在检索前立即短路拦截，并返回固定的安全边界说明与就医引导语，
坚决杜绝将一般性医学证据拼装为个体化临床诊疗方案。
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

# 固定安全边界说明（版本化产品文案，不由模型生成，不随单次响应动态变化）。
FIXED_DISCLAIMER = "AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准"

# 安全策略版本号：策略规则调整时递增，写入 Run 事件日志供审计追踪与评测对齐。
POLICY_VERSION = 1

# 确定性违规前置检测（ADR 0043：个体化请求的拦截不得依赖外部模型可用性）。
# 保守否定清单：仅匹配高置信度的个体化诊疗/危险请求措辞，漏网请求仍由意图树的
# PROHIBITED 节点兜底短路；宁可漏判不可误伤一般性医学知识问答。
_PROHIBITED_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"帮(我|忙)?[^。]{0,8}(开|开个|开一份|出具)[^。]{0,6}(处方|药|诊断证明|病假条)",
        r"(我的|本人的|孩子的|家人的)[^。]{0,10}(该吃|该用|吃多少|用多少|剂量|用量)",
        r"(推荐|建议)(一下)?[^。]{0,8}(剂量|用量|用药方案)[^。]{0,6}(我|本人)",
        r"(自杀|自残|安乐死|过量服用|大剂量注射)",
    )
)


def detect_prohibited(question: str) -> bool:
    """确定性违规请求前置检测：命中否定清单即返回 True（在调用任何外部模型之前执行）。

    匹配前去除全部空白字符：容忍「处 方」式插空格绕过；零宽字符等其他归一化
    未在此处理，漏网请求由意图树的 PROHIBITED 节点兜底短路（宁可漏判不可误伤）。
    """
    text = re.sub(r"\s+", "", question).lower()
    return any(pattern.search(text) is not None for pattern in _PROHIBITED_PATTERNS)


class RiskClass(enum.StrEnum):
    """意图触达时的医疗安全风险等级枚举。"""

    GENERAL = "general"  # 一般医学普及知识：执行正常证据检索流水线 + 基线安全边界说明
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


# 范围提示与升级用语为预设产品文案（可随设计规范微调）；固定安全边界说明除外（固定基线文本）。
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
    """生成 PROHIBITED 短路分支的固定安全引导响应：就医引导语 + 安全边界说明。"""
    if not assessment.prohibited:
        raise ValueError("仅 PROHIBITED 评估可生成短路响应")
    return f"{_ESCALATION[RiskClass.PROHIBITED]}\n{FIXED_DISCLAIMER}"
