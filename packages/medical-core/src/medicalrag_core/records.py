"""领域记录实体：会话、用户反馈、事务性 Outbox。

这三类记录此前各占一个单文件包（`conversation/`/`feedback/`/`outbox/`），
均为「一条记录」形态、无兄弟模块，故按 ADR 0060 的 deletion test 收敛到本模块：
包目录保留给拥有多个模块的领域，单概念记录不再各自占用目录。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# --- 会话（Conversation；规范用户故事 16） ---
#
# 会话保障多轮问答的记忆连续性。Thread 映射（ConversationRef）在 v1 未接入 Agent 写路径，
# 按 YAGNI 不在领域端口暴露。


@dataclass(frozen=True, slots=True)
class Conversation:
    """用户会话实体；title 用于在前端侧边栏展示。"""

    id: str
    user_id: str
    workspace_id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None


# --- 用户反馈（规范用户故事 18） ---
#
# 针对模型回答提交正向/负向反馈，供检索质量评估与生成审核。


class FeedbackValue(enum.StrEnum):
    """反馈极性枚举（点赞 / 点踩）。"""

    LIKE = "like"
    DISLIKE = "dislike"


@dataclass(frozen=True, slots=True)
class Feedback:
    """用户针对单条助手回答的反馈实体；comment 为可选的文字说明。"""

    id: str
    message_id: str
    conversation_id: str
    user_id: str
    workspace_id: str
    value: FeedbackValue
    comment: str | None = None
    created_at: str | None = None


# --- 事务性 Outbox（实现方案 §1.7） ---
#
# Outbox 消息与业务状态在同一个本地数据库事务中写入；事务成功提交后，由后台 Relay 进程
# 批量领取并异步投递至 TaskIQ 任务队列。领取采用「行锁 + 领取租约（claimed_at）」：
# 同事务提交前持有行锁（并发 relay 互斥），崩溃后租约过期自动重投；任务投递成功后回写
# `processed_at` 时间戳。具体的 SQL 实现与 Relay 驱动见 infra 及 worker 应用。


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
