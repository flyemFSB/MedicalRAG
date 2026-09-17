"""RFC 9562 UUIDv7：Python 3.12 无 stdlib uuid7，领域层用本实现统一业务主键（ADR 0066）。"""

from __future__ import annotations

import os
import time
import uuid

__all__ = ["uuid7"]


def uuid7() -> uuid.UUID:
    """生成时间有序的 UUIDv7（48-bit unix ms + 随机位，variant/version 按 RFC 9562）。"""
    timestamp_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand = bytearray(os.urandom(10))
    raw = timestamp_ms.to_bytes(6, "big") + bytes(rand)
    b = bytearray(raw)
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(b))
