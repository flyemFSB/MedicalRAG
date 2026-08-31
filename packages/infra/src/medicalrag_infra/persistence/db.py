"""SQLAlchemy 异步数据库引擎与会话工厂（实现方案 §1.4 数据库访问规范）。

每个 Worker 进程或应用上下文维护独立的 AsyncEngine 实例（严禁跨异步事件循环共享）；
数据库会话统一配置 ``expire_on_commit=False``，避免提交事务后触发额外的惰性加载查询。
引擎生命周期由外部调用方（应用组合根）统一管理，在应用停机时执行 dispose 释放连接池。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_and_session_factory(
    url: str, *, echo: bool = False
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """创建异步数据库引擎与会话工厂；返回 (engine, session_factory) 元组，组合根负责在关闭时清理 engine。"""
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory
