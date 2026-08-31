"""为 documents 表增加 published 发布状态标志列（用于文档生命周期管理与检索可见性控制）。

Revision ID: b7f2a9d1c4e8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f2a9d1c4e8"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移：为 documents 表新增 published 列（已有存量记录默认保持可检索，server_default 为 true）。"""
    op.add_column(
        "documents",
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """回滚迁移：删除 documents 表的 published 列。"""
    op.drop_column("documents", "published")
