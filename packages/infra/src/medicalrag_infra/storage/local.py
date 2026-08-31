"""本地文件系统对象存储适配器（v1 默认实现；ADR 0075 明确的 ObjectStorage 适配器）。

存储 Key 统一采用 uuid7 生成并以工作区进行目录隔离（ADR 0033 规范）：{workspace_id}/{uuid7}。
专用于开发与测试环境；生产环境可平滑切换为 S3 兼容后端，协议端口保持不变。
本地磁盘阻塞 I/O 操作统一经由 asyncio.to_thread 线程池隔离调度（开发规范 §1.4 异步规范）。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from medicalrag_core.storage.ports import ObjectRef


class LocalObjectStorage:
    """基于本地文件系统实现的 ObjectStorage 协议端口适配器。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, ref: ObjectRef) -> Path:
        return self._root / ref.workspace_id / ref.key

    async def put(self, workspace_id: str, data: bytes, *, content_type: str) -> ObjectRef:
        key = str(uuid.uuid7())
        path = self._root / workspace_id / key
        await asyncio.to_thread(self._write, path, data)
        return ObjectRef(workspace_id=workspace_id, key=key)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, ref: ObjectRef) -> bytes:
        return await asyncio.to_thread(self._read, self._path_for(ref))

    @staticmethod
    def _read(path: Path) -> bytes:
        if not path.is_file():
            raise FileNotFoundError(f"对象存储文件不存在: {path}")
        return path.read_bytes()
