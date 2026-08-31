"""为 outbox 表增加 attempts 重试次数计数列（用于毒消息监控排查与重试熔断策略，ADR 0080）。

Revision ID: c8d9e0f1a2b3
Revises: b7f2a9d1c4e8
Create Date: 2026-08-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7f2a9d1c4e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移：为 outbox 表新增 attempts 列（Worker Relay 依据此字段跳过超限的毒消息，ADR 0080）。"""
    op.add_column(
        "outbox",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """回滚迁移：删除 outbox 表的 attempts 列。"""
    op.drop_column("outbox", "attempts")
