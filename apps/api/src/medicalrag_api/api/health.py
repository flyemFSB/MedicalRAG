"""系统健康检查端点（遵循最佳实践规范：存活性探针与就绪性探针分离）。

/healthz 存活探针仅验证 API 进程处于存活状态；
/ready 就绪探针检测核心依赖服务（PostgreSQL / Redis / Qdrant）的连通性；依赖服务异常时自动报告 degraded 降级状态（返回 HTTP 200）。
可观测性依赖采用 fail-open 策略，不纳入就绪探针门禁。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    """进程存活性探针：确认 API 服务进程处于正常监听运行状态。"""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """服务就绪性探针：检测 PostgreSQL 数据库、Redis 缓存与 Qdrant 向量数据库连通性（异常时降级为 degraded 状态，HTTP 200）。"""
    checks: dict[str, str] = {}
    try:
        session_factory = request.app.state.session_factory
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "degraded"
    redis_client = request.app.state.redis_client
    redis_available = request.app.state.redis_available
    if redis_available and redis_client is not None:
        try:
            await redis_client.ping()
            checks["redis"] = "healthy"
        except Exception:
            checks["redis"] = "degraded"
    else:
        # 显式本地降级策略（架构设计：本地优雅降级 + degraded 状态指示），不静默掩盖
        checks["redis"] = "degraded"
    qdrant_client = request.app.state.qdrant_client
    if qdrant_client is not None:
        try:
            # 同步客户端：必须隔离到线程池，否则阻塞事件循环（检索适配器同样处理）
            await asyncio.to_thread(qdrant_client.get_collections)
            checks["qdrant"] = "healthy"
        except Exception:
            checks["qdrant"] = "degraded"
    status = "healthy" if all(value == "healthy" for value in checks.values()) else "degraded"
    return JSONResponse({"status": status, "checks": checks}, status_code=200)
