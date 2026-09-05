"""事务性 Outbox 领域实体与仓储端口（实现方案 §1.7）。

Outbox 消息与业务状态在同一个本地数据库事务中写入；事务成功提交后，由后台 Relay 进程批量领取并异步投递至 TaskIQ 任务队列。
领取采用 `FOR UPDATE SKIP LOCKED` 机制防范并发冲突，任务投递成功后回写 `processed_at` 时间戳。
领域层在此定义事件消息实体与仓储协议；具体的 SQL 实现与 Relay 驱动见 infra 及 worker 应用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """待投递的领域事件消息；payload 为 JSON 可序列化的字典。

    ``attempts`` 记录 Relay 投递失败的累计次数（投递成功后即标记为 processed）；
    若失败次数超过配置的最大重试上限，该消息将被跳过并保持未处理状态，供操作员人工排查。
    """

    id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, object]
    created_at: str | None = None
    processed_at: str | None = None
    attempts: int = 0

    @property
    def job_id(self) -> str:
        """稳定的 TaskIQ Job ID：格式为 outbox:{id}，用于任务排重（kicker().with_task_id）。"""
        return f"outbox:{self.id}"


class OutboxRepository(Protocol):
    """事务性 Outbox 仓储端口：支持同事务追加、批量认领未处理消息、标记处理完成及记录投递失败。"""

    async def append(self, message: OutboxMessage) -> None: ...
    async def claim(
        self, limit: int, *, max_attempts: int | None = None
    ) -> tuple[OutboxMessage, ...]: ...
    async def mark_processed(self, message_id: str) -> None: ...
    async def record_failure(self, message_id: str) -> None: ...
