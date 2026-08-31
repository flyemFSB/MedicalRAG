"""重命名 chat_runs.langfuse_trace_id 为 trace_id（遵循 ADR 0082 规范，保持可观测性后端中立）。

Revision ID: e4f5a6b7c8d9
Revises: c8d9e0f1a2b3
Create Date: 2026-08-29 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移：将 chat_runs 表中的 langfuse_trace_id 列重命名为 trace_id（支持 Phoenix 或自建 Tracing 系统，ADR 0082）。"""
    op.alter_column("chat_runs", "langfuse_trace_id", new_column_name="trace_id")


def downgrade() -> None:
    """回滚迁移：将 trace_id 列名还原为 langfuse_trace_id。"""
    op.alter_column("chat_runs", "trace_id", new_column_name="langfuse_trace_id")
