"""意图树持久化仓储适配器（以 PostgreSQL 作为配置真相来源）。"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_core.intent.tree import IntentTree
from medicalrag_core.safety.policy import RiskClass

from .models import IntentNodeRow


class SqlIntentTreeRepository:
    """从 PostgreSQL 数据库加载意图节点配置并组装内存 IntentTree 实例（PostgreSQL 为唯一事实来源）。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def load(self) -> IntentTree:
        async with self._sessions() as session:
            rows = (await session.execute(select(IntentNodeRow))).scalars().all()
        nodes = tuple(self._to_node(row) for row in rows)
        return IntentTree(nodes)

    async def list_nodes(self) -> tuple[IntentNode, ...]:
        """运营管理控制台：按节点 ID 排序查询全部意图节点列表（含未启用的禁用节点）。"""
        async with self._sessions() as session:
            rows = (
                (await session.execute(select(IntentNodeRow).order_by(IntentNodeRow.id)))
                .scalars()
                .all()
            )
        return tuple(self._to_node(row) for row in rows)

    async def update_node(self, node: IntentNode) -> None:
        """运营管理控制台：更新指定意图节点的可配置业务字段（配置数据变更）。"""
        async with self._sessions() as session:
            row = await session.get(IntentNodeRow, node.id)
            if row is None:
                raise KeyError(f"意图节点不存在: {node.id}")
            row.level = node.level.value
            row.kind = node.kind.value
            row.name = node.name
            row.description = node.description
            row.parent_id = node.parent_id
            row.examples = list(node.examples)
            row.enabled = node.enabled
            row.prompt_template = node.prompt_template
            row.safety_class = node.safety_class.value
            await session.commit()

    @staticmethod
    def _to_node(row: IntentNodeRow) -> IntentNode:
        return IntentNode(
            id=row.id,
            level=IntentLevel(row.level),
            kind=IntentKind(row.kind),
            name=row.name,
            description=row.description or "",
            parent_id=row.parent_id,
            examples=tuple(row.examples or ()),
            enabled=row.enabled,
            prompt_template=row.prompt_template,
            safety_class=RiskClass(row.safety_class),
        )


class TtlIntentTreeLoader:
    """带 TTL 的意图树加载器（可调用对象）：运营台改树后最多 TTL 秒在线生效，无需重启进程。

    供 ChatPipeline 的 ``tree_loader`` 注入；每次 Run 开始时调用一次。
    TTL 过期即整树重载（单条 SELECT，成本可忽略），TTL 胜过失效广播接线。
    """

    _TTL_S = 30.0

    def __init__(self, repo: SqlIntentTreeRepository) -> None:
        self._repo = repo
        self._tree: IntentTree | None = None
        self._loaded_at = float("-inf")

    async def __call__(self) -> IntentTree:
        if self._tree is None or time.monotonic() - self._loaded_at > self._TTL_S:
            self._tree = await self._repo.load()
            self._loaded_at = time.monotonic()
        return self._tree
