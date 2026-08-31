"""模型目标（Model Target）实体与熔断器状态模型（规范定义：Model Target / 三态熔断器）。

CircuitState 与 CircuitPolicy 为纯领域确定性值对象；熔断器的实时运行状态（如连续成功/失败计数、熔断冷却超时等）
由 infra 层的 Redis 适配器统一维护，领域层仅负责定义状态语义与状态推进策略。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CircuitState(enum.StrEnum):
    """模型目标健康熔断器的三态模型（规范用户故事 27）。"""

    CLOSED = "closed"  # 正常闭合态：放行请求并统计健康指标
    OPEN = "open"  # 熔断开启态：连续失败达到阈值，拒绝放行（快速失败）
    HALF_OPEN = "half_open"  # 半开探测态：冷却超时后试放探测请求验证服务恢复情况


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

    @property
    def circuit_allows(self) -> bool:
        """判定当前熔断状态是否允许向该模型目标分发请求。"""
        return self.circuit is CircuitState.CLOSED or self.circuit is CircuitState.HALF_OPEN


@dataclass(frozen=True, slots=True)
class CircuitPolicy:
    """模型熔断策略参数：包含熔断开启阈值、半开冷却超时及半开试探最大次数。"""

    failure_threshold: int = 5
    open_timeout_s: float = 30.0
    half_open_max: int = 1


def next_state(
    current: CircuitState, *, success: bool, failures: int, policy: CircuitPolicy
) -> tuple[CircuitState, int]:
    """确定性熔断状态推进计算。

    - CLOSED（闭合）：失败累计达阈值 → OPEN（开启，重置失败计数）；调用成功 → 失败计数归零。
    - OPEN（开启）：不随单次调用改变状态（由后台冷却定时器达到 open_timeout_s 后转为 HALF_OPEN）。
    - HALF_OPEN（半开）：试探成功 → CLOSED（恢复闭合）；试探失败 → OPEN（再次熔断）。
    """
    if current is CircuitState.CLOSED:
        if success:
            return CircuitState.CLOSED, 0
        failures += 1
        if failures >= policy.failure_threshold:
            return CircuitState.OPEN, 0
        return CircuitState.CLOSED, failures
    if current is CircuitState.HALF_OPEN:
        return (CircuitState.CLOSED, 0) if success else (CircuitState.OPEN, 0)
    return current, failures
