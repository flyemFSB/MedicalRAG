"""MinerU Cloud API 客户端适配器（基于官方 v4 API 规范）。

封装针对复杂医学文档（PDF / 扫描件）的版面分析与结构化 Markdown 提取任务：
- POST /api/v4/file-urls/batch —— 申请预签名批量上传链接；
- GET /api/v4/extract-results/batch/{batch_id} —— 获取批次解析状态并下载成果压缩包。

失败时统一映射并抛出 ProviderUnavailableError；服务凭据仅通过环境或安全配置注入。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx2 as httpx  # 全仓自有 HTTP 通信统一采用 httpx2（供应链基线）

from medicalrag_core.chat.ports import ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class MinerUConfig:
    """MinerU API 服务配置；token 仅通过环境变量或安全凭据管理器注入，严禁硬编码。"""

    base_url: str
    token: str | None = None
    timeout_s: float = 60.0


class MinerUClient:
    """基于 httpx 实现的 MinerU Cloud v4 客户端。"""

    def __init__(
        self, config: MinerUConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {config.token}"} if config.token else {},
        )

    async def aclose(self) -> None:
        """释放底层 HTTP 连接池（组合根停机时调用）。"""
        await self._client.aclose()

    async def request_file_upload(self, filename: str) -> tuple[str, str]:
        """申请文件预签名批量上传链接（POST /api/v4/file-urls/batch），返回 (batch_id, upload_url) 元组。"""
        try:
            response = await self._client.post(
                "/api/v4/file-urls/batch",
                json={"files": [filename]},
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload["batch_id"]), str(payload["file_urls"][0])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc

    async def upload_bytes(self, upload_url: str, content: bytes) -> None:
        """将本地文件字节流以 PUT 请求直传至官方预签名上传地址（按照规范不显式设置 Content-Type）。"""
        try:
            response = await self._client.put(upload_url, content=content)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc

    async def batch_status(self, batch_id: str) -> str:
        """查询批次文档的整体解析状态：done / failed / pending。"""
        try:
            response = await self._client.get(f"/api/v4/extract-results/batch/{batch_id}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        files = payload.get("files") or []
        states = [str(f.get("state", "")).lower() for f in files]
        if not states:
            return "pending"
        if any(s in {"failed", "fail", "error"} for s in states):
            return "failed"
        if all(s in {"done", "finished", "succeeded"} for s in states):
            return "done"
        return "pending"

    async def download_results_to(self, batch_id: str, dest: Path | str) -> None:
        """流式下载批次解析成果归档压缩包（ZIP）至指定文件路径，不整包载入内存。"""
        try:
            response = await self._client.get(f"/api/v4/extract-results/batch/{batch_id}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        files = payload.get("files") or []
        zip_url = next((str(f["full_zip_url"]) for f in files if f.get("full_zip_url")), None)
        if not zip_url:
            raise ProviderUnavailableError("missing_full_zip_url")
        try:
            # client.stream 边收边写：成果包体积不受限于进程内存（磁盘写入经线程池隔离）
            async with self._client.stream("GET", zip_url) as response:
                response.raise_for_status()
                target = await asyncio.to_thread(open, dest, "wb")
                try:
                    async for chunk in response.aiter_bytes():
                        await asyncio.to_thread(target.write, chunk)
                finally:
                    await asyncio.to_thread(target.close)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
