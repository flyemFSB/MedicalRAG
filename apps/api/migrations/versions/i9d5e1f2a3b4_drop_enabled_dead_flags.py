"""删除无关闭路径的死列：sample_questions.enabled、query_term_mappings.enabled。

Revision ID: i9d5e1f2a3b4
Revises: h8c4d0e3f6a7
Create Date: 2026-09-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i9d5e1f2a3b4"
down_revision: str | Sequence[str] | None = "h8c4d0e3f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移（ponytail-audit）：两列永远写 True，无 disable API/仓储方法。"""
    op.drop_column("sample_questions", "enabled")
    op.drop_column("query_term_mappings", "enabled")


def downgrade() -> None:
    """回滚迁移：恢复两列（默认启用）。"""
    op.add_column(
        "sample_questions",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "query_term_mappings",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
