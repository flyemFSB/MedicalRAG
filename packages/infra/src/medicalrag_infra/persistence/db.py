"""SQLAlchemy 异步数据库引擎与会话工厂（实现方案 §1.4 数据库访问规范）。

每个 Worker 进程或应用上下文维护独立的 AsyncEngine 实例（严禁跨异步事件循环共享）；
数据库会话统一配置 ``expire_on_commit=False``，避免提交事务后触发额外的惰性加载查询。
引擎生命周期由外部调用方（应用组合根）统一管理，在应用停机时执行 dispose 释放连接池。
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_and_session_factory(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """创建异步数据库引擎与会话工厂；返回 (engine, session_factory) 元组，组合根负责在关闭时清理 engine。

    SQLite（测试/本地）不适用池参数，并强制开启外键约束——
    SQLite 默认不强制 FK，关闭该 pragma 会让级联删除等约束缺陷在测试中假绿。
    """
    is_sqlite = url.startswith("sqlite")
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        **(
            {}
            if is_sqlite
            else {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
            }
        ),
    )
    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory
