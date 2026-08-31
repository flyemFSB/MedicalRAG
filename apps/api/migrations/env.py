"""Alembic 数据库迁移运行环境配置。

支持在线（online）与离线（offline）两种迁移模式；
数据库连接串优先从环境变量 `MEDICALRAG_DATABASE_URL` 读取，以便在 Compose、CI 及本地测试等多环境中灵活切换。
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from medicalrag_infra.persistence.models import Base

# Alembic 运行时配置对象
config = context.config

# 数据库连接串可由环境变量 MEDICALRAG_DATABASE_URL 显式覆盖
if os.environ.get("MEDICALRAG_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["MEDICALRAG_DATABASE_URL"])

# 配置日志记录器
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 挂载 SQLAlchemy 模型元数据，支持 autogenerate 模式自动对比生成差异迁移
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式运行迁移：直接输出待执行的 SQL 脚本，无需依赖可用的数据库物理连接。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线异步模式运行迁移：创建异步引擎并在连接事务中应用迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式迁移入口。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
