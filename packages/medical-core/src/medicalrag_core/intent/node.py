"""动态意图树节点实体定义（遵循规范及决策，对齐动态意图树模型）。

节点为动态意图树的基本构成单元；在执行分类打分时，仅允许启用的叶子节点（enabled leaves）参与打分匹配。
系统将下游路由划分为知识库检索（knowledge）、系统预设（system）与工具调用（tool）三类。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ..safety.policy import RiskClass
from .slot import SlotSchema


class IntentKind(enum.StrEnum):
    """意图节点所映射的下游路由类别。"""

    KNOWLEDGE = "knowledge"  # 知识库混合检索路径
    SYSTEM = "system"  # 系统预设交互与规则响应路径
    TOOL = "tool"  # 外部工具调用路径


class IntentLevel(enum.StrEnum):
    """意图树的层级结构（包含 DOMAIN / CATEGORY / TOPIC 三级）。"""

    DOMAIN = "domain"
    CATEGORY = "category"
    TOPIC = "topic"


@dataclass(frozen=True, slots=True)
class IntentNode:
    """动态意图树节点。

    ``safety_class`` 规定触发该意图时的医疗安全等级（见 safety.policy），默认为 GENERAL；
    ``slot_schema`` 为该意图关联的参数槽位抽取模式。
    """

    id: str
    level: IntentLevel
    kind: IntentKind
    name: str
    description: str = ""
    parent_id: str | None = None
    examples: tuple[str, ...] = ()
    enabled: bool = True
    prompt_snippet: str | None = None
    prompt_template: str | None = None
    slot_schema: SlotSchema | None = None
    safety_class: RiskClass = RiskClass.GENERAL
