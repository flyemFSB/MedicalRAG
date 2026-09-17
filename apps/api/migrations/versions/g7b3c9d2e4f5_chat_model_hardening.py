"""生产化加固：熔断开启时间、聊天证据落库、会话摘要水位与运行中 Run 唯一约束。

Revision ID: g7b3c9d2e4f5
Revises: f2a4c6d8e0b1
Create Date: 2026-09-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7b3c9d2e4f5"
down_revision: str | Sequence[str] | None = "f2a4c6d8e0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移：
    - model_targets.circuit_opened_at：熔断开启时间（冷却后翻转 HALF_OPEN 放行探测）；
    - chat_runs.question / chat_runs.evidence：用户问题与命中证据落库（运营追踪与反馈溯源）；
    - conversations.summary_offset：记忆摘要增量压缩水位；
    - uq_chat_runs_running：同一会话至多一条非终态 Run（并发重复提交幂等防护）。
    """
    op.add_column(
        "model_targets",
        sa.Column("circuit_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("chat_runs", sa.Column("question", sa.Text(), nullable=True))
    op.add_column("chat_runs", sa.Column("evidence", sa.JSON(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("summary_offset", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_chat_runs_running",
        "chat_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('completed', 'cancelled', 'failed')"),
        sqlite_where=sa.text("status NOT IN ('completed', 'cancelled', 'failed')"),
    )


def downgrade() -> None:
    """回滚迁移：删除上述列与部分唯一索引。"""
    op.drop_index("uq_chat_runs_running", table_name="chat_runs")
    op.drop_column("conversations", "summary_offset")
    op.drop_column("chat_runs", "evidence")
    op.drop_column("chat_runs", "question")
    op.drop_column("model_targets", "circuit_opened_at")
