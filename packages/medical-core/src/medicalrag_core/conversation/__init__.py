"""会话（Conversation）领域实体与仓储端口（规范定义：Conversation = 持久化的用户多轮交互历史序列；用户故事 16）。

会话（Conversation）保障多轮问答的记忆连续性，并在不同病例之间维护独立的隔离边界；
Thread 为 Agent 运行时执行与恢复会话的有状态运行上下文（由 Aegra 统一托管）。
领域层在此定义业务侧 Conversation 实体，以及业务会话与底层 Thread 映射关联所需的最小契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Conversation:
    """用户会话实体；title 用于在前端侧边栏展示。"""

    id: str
    user_id: str
    workspace_id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationRef:
    """业务会话与 Aegra 运行时 Thread 的映射记录（业务主键由 PostgreSQL 拥有）。"""

    conversation_id: str
    thread_id: str


class ConversationRepository(Protocol):
    """会话数据持久化访问端口。"""

    async def create(self, conversation: Conversation) -> Conversation: ...
    async def get(self, conversation_id: str) -> Conversation | None: ...
    async def list_for_user(self, user_id: str) -> tuple[Conversation, ...]: ...
    async def touch(self, conversation_id: str) -> None: ...
    async def save_thread(self, ref: ConversationRef) -> None: ...
    async def thread_of(self, conversation_id: str) -> str | None: ...
