"""Alembic 迁移检查（spec：schema 可从空数据库创建）。"""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

_ALEMBIC_INI = "apps/api/alembic.ini"


def test_migration_creates_schema_from_empty_database(tmp_path, monkeypatch):
    # 隔离宿主环境：env.py 会用 MEDICALRAG_DATABASE_URL 覆盖 ini，这里显式清除。
    monkeypatch.delenv("MEDICALRAG_DATABASE_URL", raising=False)
    db_file = tmp_path / "migration.db"
    config = Config(_ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file}")
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{db_file}"))
    tables = set(inspector.get_table_names())
    assert {
        "chat_runs",
        "run_events",
        "messages",
        "users",
        "intent_nodes",
        "ingestion_runs",
        "ingestion_run_stages",
    } <= tables
