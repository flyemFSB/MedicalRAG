"""度量指标导出 API 路由：/metrics（Prometheus 标准抓取格式）。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus 监控抓取端点（官方 generate_latest 文本；严格脱敏：仅指标名与数值）。"""
    return Response(
        content=request.app.state.metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
