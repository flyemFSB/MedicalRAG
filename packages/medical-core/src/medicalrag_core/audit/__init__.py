"""操作审计领域实体（管理后台审计功能）。

记录谁（Actor）在何时对何种业务实体执行了何种操作；正文内容、敏感医疗实体及凭据严禁写入审计详情（严格遵循规范 §3 日志与审计红线）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """操作审计记录实体。"""

    id: str
    actor_user_id: str
    actor_email: str
    workspace_id: str
    action: str
    entity_type: str
    entity_name: str
    detail: str
    created_at: str | None = None
