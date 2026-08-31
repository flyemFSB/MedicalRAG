"""意图槽位模式定义与确定性提取（规范定义：意图特定槽位提取机制）。

槽位（Slot）为意图节点关联的可选参数约束（SlotSchema），用于细化检索条件与增强上下文，严禁承载任何个体化临床决策逻辑。
当必填槽位缺失时，系统将跳过依赖该槽位的落地动作，并引导用户补充信息，同时保留其他独立的子意图。
槽位提取为纯函数逻辑：对结构化模型输出执行严格的类型与枚举强制校验，非法值被明确记录而非静默丢弃。
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass


class SlotType(enum.StrEnum):
    """槽位数据类型枚举。"""

    STRING = "string"
    INTEGER = "integer"
    ENUM = "enum"


@dataclass(frozen=True, slots=True)
class SlotDefinition:
    """单个槽位定义：包含槽位名称、类型、是否必填、枚举候选值列表及用途说明。"""

    name: str
    slot_type: SlotType
    required: bool = False
    enum_values: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class SlotSchema:
    """意图节点关联的槽位模式定义（版本化配置数据）。"""

    slots: tuple[SlotDefinition, ...]


@dataclass(frozen=True, slots=True)
class SlotFilling:
    """单次槽位提取结果：包含合法值映射、缺失的必填槽位列表及非法原始值记录。"""

    values: Mapping[str, object]
    missing: tuple[str, ...]
    invalid: Mapping[str, object]


def _coerce(definition: SlotDefinition, raw: object) -> object | None:
    """依据槽位定义执行类型转换与合法性校验；若转换失败则返回 None。"""
    if definition.slot_type is SlotType.INTEGER:
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
        return None
    if definition.slot_type is SlotType.ENUM:
        return raw if isinstance(raw, str) and raw in definition.enum_values else None
    return raw if isinstance(raw, str) and raw else None


def extract_slots(schema: SlotSchema, raw: Mapping[str, object]) -> SlotFilling:
    """根据模式对原始输入提取槽位：分别归集有效值、缺失必填项与非法输入。"""
    values: dict[str, object] = {}
    missing: list[str] = []
    invalid: dict[str, object] = {}
    for definition in schema.slots:
        if definition.name not in raw:
            if definition.required:
                missing.append(definition.name)
            continue
        coerced = _coerce(definition, raw[definition.name])
        if coerced is None:
            invalid[definition.name] = raw[definition.name]
        else:
            values[definition.name] = coerced
    return SlotFilling(values, tuple(missing), invalid)
