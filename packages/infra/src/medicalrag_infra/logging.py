"""安全结构化日志模块（遵循开发规范 §3 审计红线；基于 loguru 实现，优先采用标准与高质量三方库）。

白名单校验落在**唯一输出汇聚点** `_format`：loguru 的 `extra` 只能来自业务绑定，
因此被禁字段（原始 prompt、文档正文、凭据等）与未登记字段一律不落盘。
放在汇聚点而非绑定调用处，是为了让绕过校验的调用（直接 `logger.bind(...)`）也无法泄漏。
"""

from __future__ import annotations

import sys
import traceback

from loguru import logger

# 允许落盘的关联字段与度量元数据白名单（遵循规范 §3）。
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


def _format(record) -> str:
    """格式化单条日志输出：`时间 级别 消息 key=value...` + 异常堆栈。

    loguru 仅在 format 为**字符串**时自动追加换行与 `{exception}`；函数式 format 必须自己渲染，
    否则 `logger.exception()` 的 traceback 不会落盘。
    """
    extra = " ".join(
        f"{key}={value}" for key, value in record["extra"].items() if key in SAFE_FIELDS
    )
    base = f"{record['time']:%Y-%m-%d %H:%M:%S} {record['level'].name: <8} {record['message']}"
    line = base + (f" {extra}" if extra else "") + "\n"
    if record["exception"] is not None:
        line += "".join(traceback.format_exception(*record["exception"]))
    return line


def configure(level: str = "INFO") -> None:
    """配置全局 loguru logger 实例：移除默认输出，挂载符合安全格式的 stderr 输出流（在应用进程启动时调用一次）。

    `diagnose=False` 是生产 recipe：loguru 默认会在异常里 dump 局部变量，可能泄漏凭据
    （见 loguru resources/recipes）。即使当前 `_format` 自渲染堆栈，也显式关闭，防止日后
    改回字符串 format（`{exception}`）时静默打开泄露路径。
    """
    logger.remove()
    logger.add(sys.stderr, format=_format, level=level, diagnose=False)


__all__ = [
    "SAFE_FIELDS",
    "configure",
    "logger",
]
