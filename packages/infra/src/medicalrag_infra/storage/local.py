"""本地文件系统对象存储适配器（v1 默认实现；ObjectStorage 适配器）。

存储 Key 统一采用 uuid7 生成并以工作区进行目录隔离：{workspace_id}/{uuid7}。
专用于开发与测试环境；生产环境可平滑切换为 S3 兼容后端，协议端口保持不变。
本地磁盘阻塞 I/O 操作统一经由 asyncio.to_thread 线程池隔离调度（开发规范 §1.4 异步规范）。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from medicalrag_core.ids import uuid7
from medicalrag_core.storage.ports import ObjectRef


class LocalObjectStorage:
    """基于本地文件系统实现的 ObjectStorage 协议端口适配器。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, ref: ObjectRef) -> Path:
        return self._root / ref.workspace_id / ref.key

    async def put(self, workspace_id: str, data: bytes, *, content_type: str) -> ObjectRef:
        key = str(uuid7())
        path = self._root / workspace_id / key
        await asyncio.to_thread(self._write, path, data)
        return ObjectRef(workspace_id=workspace_id, key=key)

    async def put_file(self, workspace_id: str, file, *, content_type: str) -> ObjectRef:
        """流式落盘上传：分块读取文件对象写出，不将整份文件载入内存（大文件上传 OOM 防护）。

        ``file`` 为具备同步 ``read(n)`` 的二进制文件对象（如 SpooledTemporaryFile）；
        该方法为本地适配器的能力扩展，未纳入 ObjectStorage 协议端口（S3 后端改用 multipart API）。
        """
        key = str(uuid7())
        path = self._root / workspace_id / key
        await asyncio.to_thread(self._write_stream, path, file)
        return ObjectRef(workspace_id=workspace_id, key=key)

    @staticmethod
    def _write_stream(path: Path, file) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "wb") as target:
                while chunk := file.read(1024 * 1024):
                    target.write(chunk)
        except BaseException:
            # 上传中断（客户端断开/磁盘满）不留半截文件：
            # 孤儿对账的 1h 新近度保护会跳过新文件，半截文件将永久残留
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, ref: ObjectRef) -> bytes:
        return await asyncio.to_thread(self._read, self._path_for(ref))

    async def get_stream(self, ref: ObjectRef, *, chunk_size: int = 1024 * 1024):
        """流式读取对象内容（异步分块产出；大文件预览/下载的 OOM 防护）。

        本地适配器能力扩展（同 put_file），未纳入 ObjectStorage 协议端口；
        每个 1MB 块的磁盘读取经 asyncio.to_thread 隔离，不阻塞事件循环。
        """
        path = self._path_for(ref)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError(f"对象存储文件不存在: {path}")
        iterator = self._iter_chunks(path, chunk_size)
        while True:
            try:
                chunk = await asyncio.to_thread(next, iterator)
            except StopIteration:
                return
            yield chunk

    @staticmethod
    def _iter_chunks(path: Path, chunk_size: int):
        with open(path, "rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    async def scan_orphans(self, referenced_keys: set[str], *, min_age_s: int = 3600) -> int:
        """孤儿对象对账：删除引用集之外且修改时间早于 min_age_s 的文件，返回清理数量。

        ``referenced_keys`` 为全工作区统一的对象 Key 集合（Key 全局唯一，uuid7 生成）；
        min_age_s 保护"上传事务已提交但 Run 元数据尚未落库"的竞态窗口。
        """
        return await asyncio.to_thread(self._scan_orphans, referenced_keys, min_age_s)

    def _scan_orphans(self, referenced_keys: set[str], min_age_s: int) -> int:
        removed = 0
        now = time.time()
        if not self._root.is_dir():
            return 0
        for workspace_dir in self._root.iterdir():
            if not workspace_dir.is_dir():
                continue
            for file in workspace_dir.iterdir():
                if not file.is_file() or file.name in referenced_keys:
                    continue
                if now - file.stat().st_mtime < min_age_s:
                    continue
                file.unlink()
                removed += 1
        return removed

    @staticmethod
    def _read(path: Path) -> bytes:
        if not path.is_file():
            raise FileNotFoundError(f"对象存储文件不存在: {path}")
        return path.read_bytes()
