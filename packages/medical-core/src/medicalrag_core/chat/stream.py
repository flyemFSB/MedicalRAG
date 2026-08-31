"""聊天编排的类型化流式事件（规范定义：编排器返回结构化结果或异步类型事件流）。

事件发射顺序与 `ChatPipeline.run_stream` 的确定性执行阶段完全一致；
浏览器端经 Aegra v2 通道（Graph State 的 values / custom channels）进行消费，本模块为领域层的事实来源。
每个事件均内建 ``sse_name`` 与 ``to_payload`` 方法（ADR 0080）：FastAPI SSE 端点与 Agent Graph
共享同一序列化出口，保证新增字段时前后端契约零遗漏。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ..evidence.evidence import Evidence
from ..safety.policy import SafetyAssessment
from .model import Analysis, ChatResult


@dataclass(frozen=True, slots=True)
class AnalysisEvent:
    """意图分析完成事件：包含重写问题、候选意图、提取槽位及引导文案。"""

    sse_name: ClassVar[str] = "analysis"

    analysis: Analysis

    def to_payload(self) -> dict[str, object]:
        return self.analysis.to_payload()


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    """证据就绪事件：检索与融合完成，进入模型上下文的最终证据（Evidence）集合。"""

    sse_name: ClassVar[str] = "evidence"

    evidence: tuple[Evidence, ...]

    def to_payload(self) -> dict[str, object]:
        return {"evidence": [e.to_payload() for e in self.evidence]}


@dataclass(frozen=True, slots=True)
class SafetyEvent:
    """安全评估事件：包含风险等级、范围提示与升级用语，独立于模型生成文本对外输出。"""

    sse_name: ClassVar[str] = "safety"

    safety: SafetyAssessment

    def to_payload(self) -> dict[str, object]:
        return self.safety.to_payload()


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """回答增量事件：单段回答文本 Token 增量（ADR 0041：直接流式直出，不设阻塞缓冲门）。"""

    sse_name: ClassVar[str] = "token"

    text: str

    def to_payload(self) -> dict[str, object]:
        return {"text": self.text}


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Run 终止完成事件：包含完整回答文本、Run ID、证据列表、安全提示及审计元数据。"""

    sse_name: ClassVar[str] = "done"

    result: ChatResult

    def to_payload(self) -> dict[str, object]:
        result = self.result
        safety = result.safety
        return {
            "outcome": result.outcome.value,
            "message": result.message,
            "run_id": result.run_id,
            "evidence": [e.to_payload() for e in result.evidence],
            "safety_notice": safety.scope_notice if safety is not None else None,
            "safety_escalation": safety.escalation if safety is not None else None,
        }


ChatStreamEvent = AnalysisEvent | EvidenceEvent | SafetyEvent | TokenEvent | DoneEvent
