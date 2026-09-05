"""对象存储适配器端口协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """对象引用标识：工作区（Workspace）作用域下具备防猜测特性的安全对象 Key。"""

    workspace_id: str
    key: str


class ObjectStorage(Protocol):
    """对象存储适配器端口：提供 put / get 能力；底层存储严格按工作区隔离，且 Key 不可猜测（多租户安全隔离）。"""

    async def put(self, workspace_id: str, data: bytes, *, content_type: str) -> ObjectRef: ...
    async def get(self, ref: ObjectRef) -> bytes: ...
