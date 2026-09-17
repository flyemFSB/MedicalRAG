"""outbox 增加领取租约列 claimed_at；清理无代码引用的 slot_schemas 死表。

1. relay 原先依赖 `SELECT ... FOR UPDATE SKIP LOCKED`，但行锁随 session 关闭立即释放，
   多个 relay 循环会领到同一批消息并重复投递。改为领取时打租约时间戳（同事务提交），
   worker 崩溃后租约过期自动重投（at-least-once）。
   轮询用的部分索引已存在（`ix_outbox_unprocessed`，见 a1b2c3d4e5f6），不重复创建。
2. `slot_schemas` 表由 a1b2c3d4e5f6 建出，但全仓无任何 Python 读写方（SlotSchema 为代码内静态定义），
   属 autogenerate 遗留；保留它会让 `alembic check` 永久报漂移。此处删除。

Revision ID: f2a4c6d8e0b1
Revises: e4f5a6b7c8d9
Create Date: 2026-09-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a4c6d8e0b1"
down_revision: str | Sequence[str] | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用迁移：新增 claimed_at 租约列；删除无引用的 slot_schemas 表。"""
    op.add_column(
        "outbox",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index(op.f("ix_slot_schemas_intent_node_id"), table_name="slot_schemas")
    op.drop_table("slot_schemas")


def downgrade() -> None:
    """回滚迁移：重建 slot_schemas 表并删除 claimed_at 列。"""
    op.create_table(
        "slot_schemas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("intent_node_id", sa.String(length=128), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_slot_schemas_intent_node_id"),
        "slot_schemas",
        ["intent_node_id"],
        unique=False,
    )
    op.drop_column("outbox", "claimed_at")
