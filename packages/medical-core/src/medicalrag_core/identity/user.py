"""用户实体定义（规范定义：User = MedicalRAG 平台自有的已认证个人账户）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    """用户账户实体；password_hash 仅用于身份凭据校验，严禁对外暴露或进入 API 响应。

    用户主键 ID 采用单调递增的 UUIDv7（ADR 0066）；email 为唯一登录标识，password_hash 由 PasswordHasher 适配器加密生成。
    """

    id: str
    email: str
    password_hash: str
