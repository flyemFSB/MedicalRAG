"""用户持久化仓储适配器：实现 medical_core.identity.ports.UserRepository 协议端口。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.identity.user import User as DomainUser

from .models import User as UserRow


class SqlUserRepository:
    """基于 SQLAlchemy 异步会话实现的用户账户仓储适配器；email 唯一性由数据库唯一键约束强力保障。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create(self, user: DomainUser) -> None:
        """持久化新建的用户实体。"""
        async with self._sessions() as session:
            session.add(
                UserRow(
                    id=uuid.UUID(user.id),
                    email=user.email,
                    password_hash=user.password_hash,
                )
            )
            await session.commit()

    async def get_by_email(self, email: str) -> DomainUser | None:
        """依据邮箱地址查询用户；若不存在返回 None。"""
        async with self._sessions() as session:
            row = await session.scalar(select(UserRow).where(UserRow.email == email))
            if row is None:
                return None
            return DomainUser(id=str(row.id), email=row.email, password_hash=row.password_hash)

    async def get_by_id(self, user_id: str) -> DomainUser | None:
        """依据用户 ID 查询用户实体；若不存在返回 None。"""
        async with self._sessions() as session:
            row = await session.get(UserRow, uuid.UUID(user_id))
            if row is None:
                return None
            return DomainUser(id=str(row.id), email=row.email, password_hash=row.password_hash)
