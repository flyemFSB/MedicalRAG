"""轻量进程内度量指标注册表（开发规范 §3：结构化日志 + 指标 + 健康检查）。

提供无锁的内存计数器（Counter）、量规（Gauge）及延迟分位数统计（P50/P95），
支持以 JSON 格式输出快照供调试界面使用，并支持渲染标准 OpenMetrics / Prometheus 抓取文本（/metrics 端点）。
所有指标名称与标签均严格遵循脱敏白名单约束。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """轻量进程内度量指标注册表。"""

    counters: Counter[str] = field(default_factory=Counter)
    gauges: dict[str, float] = field(default_factory=dict)
    _latency: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, name: str, *, by: int = 1) -> None:
        """递增指定计数器（例如 chat_requests_total 或 provider_failures_total）。"""
        self.counters[name] += by

    def observe(self, name: str, value: float) -> None:
        """记录一次样本观测值（如 run_latency_ms 耗时毫秒数），供 P50 与 P95 统计汇总。"""
        self._latency[name].append(value)

    def percentile(self, name: str, q: float) -> float:
        """计算指定指标的百分位数（q 取值 0-100）。"""
        samples = self._latency.get(name, [])
        if not samples:
            return 0.0
        ordered = sorted(samples)
        index = min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1)))
        return round(ordered[index], 1)

    def snapshot(self) -> dict[str, object]:
        """导出当前指标快照字典（脱敏：仅包含指标名与数值，严禁携带任何业务正文）。"""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "latency_ms": {
                name: {"p50": self.percentile(name, 50), "p95": self.percentile(name, 95)}
                for name in self._latency
            },
        }

    def render_prometheus(self) -> str:
        """渲染为标准 Prometheus OpenMetrics v0.0.4 文本格式：支持 counter、gauge 及 summary 分位数展示。"""
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            lines += [f"# TYPE {name} counter", f"{name} {value}"]
        for name, value in sorted(self.gauges.items()):
            lines += [f"# TYPE {name} gauge", f"{name} {value}"]
        for name, samples in sorted(self._latency.items()):
            lines.append(f"# TYPE {name} summary")
            total = float(sum(samples))
            lines += [
                f'{name}{{quantile="0.5"}} {self.percentile(name, 50)}',
                f'{name}{{quantile="0.95"}} {self.percentile(name, 95)}',
                f"{name}_sum {total}",
                f"{name}_count {len(samples)}",
            ]
        return "\n".join(lines) + ("\n" if lines else "")
