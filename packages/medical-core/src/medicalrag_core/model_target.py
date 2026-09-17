"""模型目标（Model Target）实体与熔断状态语义（规范定义：Model Target / 三态熔断器）。

单一概念模块：不单独占包目录（包目录留给拥有多个模块的领域，见 ADR 0060 deletion test）。

CircuitState 为纯领域确定性值对象；实时状态推进由 infra 的模型路由适配器（providers/routing.py）
在 Provider 失败路径上执行并持久化（closed ↔ open/half_open + 失败计数），运营后台据此展示真实健康状态。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class CircuitState(enum.StrEnum):
    """模型目标健康熔断器的三态模型（规范用户故事 27）。"""

    CLOSED = "closed"  # 正常闭合态：放行请求并统计健康指标
    OPEN = "open"  # 熔断开启态：连续失败达到阈值，拒绝放行（快速失败）
    HALF_OPEN = "half_open"  # 半开探测态：冷却后试放探测请求验证服务恢复情况


@dataclass(frozen=True, slots=True)
class ModelTarget:
    """可供聊天编排 Run 调用的模型目标与其能力集合。

    ``capabilities`` 包含模型支持的能力标签（例如 "generation"、"analysis"、"streaming"、"dense"、"rerank"）；
    ``priority`` 数值越大代表调度优先级越高；``circuit`` 记录当前熔断器状态与失败计数。
    """

    id: str
    name: str
    provider: str
    model: str
    capabilities: frozenset[str] = frozenset()
    priority: int = 0
    circuit: CircuitState = CircuitState.CLOSED
    failures: int = 0
    # 熔断开启时刻：冷却到期后由路由器翻转 HALF_OPEN 放行探测请求
    circuit_opened_at: datetime | None = None

    @property
    def circuit_allows(self) -> bool:
        """判定当前熔断状态是否允许向该模型目标分发请求。"""
        return self.circuit is CircuitState.CLOSED or self.circuit is CircuitState.HALF_OPEN
