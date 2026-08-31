"""Argon2 密码哈希适配器实现（实现方案 §1.2：采用 argon2id 算法，符合 RFC 9106 推荐安全参数）。"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import VerificationError


class Argon2PasswordHasher:
    """实现 PasswordHasher 协议端口；密码校验失败或哈希格式非法时统一返回 False，杜绝泄露具体失败步骤。"""

    def __init__(self) -> None:
        # 默认安全参数：m=64MiB 内存, t=3 迭代轮次, p=4 并行度（RFC 9106 推荐配置）
        self._hasher = _Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, encoded: str) -> bool:
        try:
            return self._hasher.verify(encoded, password)
        except VerificationError, ValueError:
            # 无论是密码不匹配（VerificationError）还是哈希格式损坏（ValueError），均模糊处理并返回 False
            return False
