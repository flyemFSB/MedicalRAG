"""删除无写方/无读方的死结构：prompt_snippet 列、platform_credentials 与 audit_events 表。

Revision ID: h8c4d0e3f6a7
Revises: g7b3c9d2e4f5
Create Date: 2026-09-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h8c4d0e3f6a7"
down_revision: str | Sequence[str] | None = "g7b3c9d2e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移（全仓 YAGNI 清理，见 ponytail-audit）：
    - intent_nodes.prompt_snippet：全栈只写不读的死列；
    - platform_credentials：无任何写入路径，GET 恒为空（ADR 0010 能力待密钥管理器接入时随写路径重建）；
    - audit_events：无任何写入路径，GET 恒为空（ADR 0018 审计写入接线时随写路径重建）。
    """
    op.drop_column("intent_nodes", "prompt_snippet")
    op.drop_table("platform_credentials")
    op.drop_table("audit_events")


def downgrade() -> None:
    """回滚迁移：重建两表与死列。"""
    op.create_table(
        "platform_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("bound_target_id", sa.Uuid(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_result", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_email", sa.String(320), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_name", sa.String(512), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("intent_nodes", sa.Column("prompt_snippet", sa.Text(), nullable=True))
