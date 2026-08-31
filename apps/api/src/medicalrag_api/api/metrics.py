"""度量指标导出 API 路由：提供 /metrics（Prometheus 标准抓取格式）与 /api/metrics（JSON 调试快照）。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus 监控抓取端点（输出 OpenMetrics v0.0.4 纯文本；严格脱敏：仅包含指标名与度量数值）。"""
    return Response(
        content=request.app.state.metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/api/metrics")
async def metrics_snapshot(request: Request) -> dict[str, object]:
    """进程内度量指标 JSON 格式快照（供开发与运维排查调试使用；监控抓取请访问 /metrics）。"""
    return request.app.state.metrics.snapshot()
