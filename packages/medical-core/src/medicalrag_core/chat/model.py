"""聊天编排核心的值对象与结果契约（规范 seam 定义）。"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ..evidence.evidence import Evidence
from ..intent.node import IntentNode
from ..intent.tree import ScoredIntent
from ..safety.policy import SafetyAssessment


class MessageRole(enum.StrEnum):
    """会话中的消息发送者角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Message:
    """会话内的单条消息记录。"""

    role: MessageRole
    text: str


@dataclass(frozen=True, slots=True)
class MemoryContext:
    """会话最近的有界记忆窗口。"""

    messages: tuple[Message, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """单次聊天请求。

    开启分析深度（Analysis Depth）仅会提升检索预算并启用证据综合，
    不会放宽安全边界，亦不改变证据回答（Evidence Answer）契约。
    """

    question: str
    conversation_id: str
    user_id: str
    workspace_id: str
    analysis_depth: bool = False


@dataclass(frozen=True, slots=True)
class Analysis:
    """意图分类器（外部模型适配器）的分析结果。

    ``guidance_message`` 为意图存疑或无法安全区分时的有界澄清引导语；
    ``system_message`` 为 SYSTEM 意图的系统预设响应文案。两者均由适配器输出，
    对于未知或格式错误的分类输出，系统一律不臆造任何意图。
    """

    rewritten_question: str
    candidates: tuple[ScoredIntent, ...]
    guidance_message: str | None = None
    system_message: str | None = None
    # 问题拆分出的子问题（问题重写 + 拆分，检索时作为附加查询文本扩展召回视角）
    sub_questions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        """对外导出的分析结果载荷（SSE 端点与 Agent Graph 共享该统一出口）。"""
        return {
            "rewritten_question": self.rewritten_question,
            "sub_questions": list(self.sub_questions),
            "intents": [{"node_id": c.node_id, "score": c.score} for c in self.candidates],
            "guidance": self.guidance_message,
        }


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """传递给生成适配器的脱敏上下文；安全评估独立传递，不拼入模型输入文本中。

    ``analysis`` 为真时表示这是一次深度分析（Analysis Depth）请求：适配器应选用
    具备高阶分析能力的模型目标进行深度综合，同时恪守安全边界与证据回答契约。
    """

    question: str
    rewritten_question: str
    evidence: tuple[Evidence, ...]
    memory: MemoryContext
    safety: SafetyAssessment | None = None
    analysis: bool = False


@dataclass(frozen=True, slots=True)
class IntentQuery:
    """单次落地检索的意图及其查询文本。

    ``rewritten_question`` 为分类器重写后的用户问题：混合检索（Hybrid Retrieval）
    的稠密与稀疏查询均以该文本为主体；
    意图节点的名称与描述仅在重写文本缺失时作为兜底，不作为查询主体。
    """

    node: IntentNode
    rewritten_question: str = ""


class Outcome(enum.StrEnum):
    """单次 Run 的终止结果类型。"""

    ANSWERED = "answered"
    GUIDANCE = "guidance"
    SYSTEM_ONLY = "system_only"
    SAFETY = "safety"
    EMPTY = "empty"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class ChatResult:
    """聊天编排的最终产出：包含终止类型、回答正文、证据集合、安全评估及追踪元数据。

    ``safety`` 包含范围提示与升级用语，由前端界面独立渲染，严禁混入模型回答正文中；
    ``trace_id`` 关联观测后端中本 Run 的记录（Aegra thread_id）。
    """

    outcome: Outcome
    message: str
    run_id: str
    evidence: tuple[Evidence, ...] = ()
    safety: SafetyAssessment | None = None
    trace_id: str | None = None
    retrieval_policy_version: int | None = None
    # 落库后的助手消息 ID：前端反馈（点赞/点踩）以此为准，保证反馈可回溯到具体消息行
    message_id: str | None = None
