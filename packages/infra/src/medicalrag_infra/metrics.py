"""进程内度量指标（prometheus_client 薄封装）。

- 计数：官方 Counter
- 延迟：官方 Histogram（分位数由 Prometheus `histogram_quantile` 侧聚合，应用内不另存样本）
- 文本：`generate_latest`；指标名不得携带业务正文
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


def _metric_name(name: str) -> str:
    """校验 Prometheus 指标名（字母/数字/下划线/冒号，不能以数字开头）。

    prometheus_client 对非法名不会报错，会静默改写（`9bad` → `_bad_total`），
    因此这里必须显式校验，否则指标名写错后线上静默丢指标。
    """
    if not name:
        raise ValueError("metric name must be non-empty")
    if not (name[0].isalpha() or name[0] == "_"):
        raise ValueError(f"invalid metric name: {name!r}")
    if not all(c.isalnum() or c in "_:" for c in name):
        raise ValueError(f"invalid metric name: {name!r}")
    return name


class Metrics:
    """进程内指标注册表（每实例独立 CollectorRegistry，便于单测）。"""

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}

    def _counter(self, name: str) -> Counter:
        metric = self._counters.get(name)
        if metric is None:
            # Counter 自动处理 _total 后缀（'x_total' → 样本 x_total；'x' → 样本 x_total）
            metric = Counter(
                name,
                f"{name} total",
                registry=self._registry,
            )
            self._counters[name] = metric
        return metric

    def _histogram(self, name: str) -> Histogram:
        metric = self._histograms.get(name)
        if metric is None:
            metric = Histogram(
                name,
                f"{name} observations",
                registry=self._registry,
                # 覆盖毫秒级延迟常见范围
                buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
            )
            self._histograms[name] = metric
        return metric

    def inc(self, name: str, *, by: int = 1) -> None:
        """递增计数器（如 chat_requests_total）。"""
        self._counter(_metric_name(name)).inc(by)

    def observe(self, name: str, value: float) -> None:
        """记录一次延迟观测（如 run_latency_ms）；分位数由 Prometheus 侧从直方图桶计算。"""
        self._histogram(_metric_name(name)).observe(value)

    def render_prometheus(self) -> str:
        """渲染 Prometheus 抓取文本（官方 generate_latest）。"""
        return generate_latest(self._registry).decode("utf-8")
