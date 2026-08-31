"""摄取运行（Ingestion Run）持久化端口（ADR 0013 / ADR 0063：PostgreSQL 作为单一事实来源；阶段推进保证幂等）。"""

from __future__ import annotations

from typing import Protocol

from .state_machine import IngestionRunState


class IngestionRunRepository(Protocol):
    """摄取运行持久化仓储：负责创建 Run、查询状态、幂等完成阶段并驱动状态单向递进。

    ``set_metadata`` 与 ``metadata`` 用于维护 Run 作用域上下文（如 object_key、title、expected_chunks、artifact_ref 等），
    随摄取阶段推进逐步写入与读取。
    """

    async def create_run(self, document_id: str, workspace_id: str) -> str: ...
    async def state(self, run_id: str) -> IngestionRunState: ...
    async def complete_stage(self, run_id: str, stage: IngestionRunState) -> IngestionRunState: ...
    async def set_metadata(self, run_id: str, key: str, value: object) -> None: ...
    async def metadata(self, run_id: str) -> dict[str, object]: ...
