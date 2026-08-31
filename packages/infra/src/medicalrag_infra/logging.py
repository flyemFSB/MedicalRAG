"""安全结构化日志模块（遵循开发规范 §3 审计红线；基于 loguru 实现，ADR 0074 优先采用标准与高质量三方库）。

`safe_bind` 在日志字段绑定前执行严格的白名单校验：对于违禁敏感字段与未知字段直接抛出 `UnsafeLogField`，
从根本上杜绝患者隐私、凭据以及未经脱敏的医疗正文内容泄露至日志。
标准关联字段包括 `request_id` / `run_id` / `workspace_id` / `job_id` / `event_id` 等；
其中 `run_id` 为业务唯一事实来源，详细观测信息统一汇聚至 Trace 后端（ADR 0082）。
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger

# 允许记录的安全关联字段与度量元数据白名单（遵循规范 §3）。
SAFE_FIELDS = frozenset(
    {
        "request_id",
        "run_id",
        "workspace_id",
        "job_id",
        "event_id",
        "conversation_id",
        "outcome",
        "status",
        "count",
        "duration_ms",
        "model",
        "provider",
        "error_class",
        "policy_version",
    }
)

# 严禁记录的敏感字段名称黑名单（覆盖规范 §3 列举的各项红线内容）。
FORBIDDEN_FIELDS = frozenset(
    {
        "prompt",
        "question",
        "answer",
        "document",
        "evidence",
        "snippet",
        "text",
        "content",
        "patient",
        "token",
        "password",
        "credential",
        "cookie",
        "authorization",
        "api_key",
        "secret",
    }
)


class UnsafeLogField(ValueError):
    """当尝试记录被禁止或未经允许的日志字段时抛出该异常。"""


def safe_bind(**fields: Any) -> dict[str, Any]:
    """校验待绑定的日志上下文元数据：若包含违禁字段或非白名单字段则直接拒绝，校验通过后返回安全字典副本。"""
    forbidden = FORBIDDEN_FIELDS & fields.keys()
    if forbidden:
        raise UnsafeLogField(f"检测到违禁敏感日志字段: {sorted(forbidden)}")
    unknown = fields.keys() - SAFE_FIELDS
    if unknown:
        raise UnsafeLogField(f"检测到未在白名单中的日志字段: {sorted(unknown)}")
    return fields


def _format(record) -> str:
    """格式化单条日志输出：`时间 级别 消息 key=value...`；仅渲染已通过 safe_bind 安全绑定的 extra 字段。"""
    extra = " ".join(f"{key}={value}" for key, value in record["extra"].items())
    base = f"{record['time']:%Y-%m-%d %H:%M:%S} {record['level'].name: <8} {record['message']}"
    return base + (f" {extra}" if extra else "")


def configure(level: str = "INFO") -> None:
    """配置全局 loguru logger 实例：移除默认输出，挂载符合安全格式的 stderr 输出流（在应用进程启动时调用一次）。"""
    logger.remove()
    logger.add(sys.stderr, format=_format, level=level)


__all__ = [
    "FORBIDDEN_FIELDS",
    "SAFE_FIELDS",
    "UnsafeLogField",
    "configure",
    "logger",
    "safe_bind",
]
