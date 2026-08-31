"""用户反馈领域实体（规范用户故事 18：针对模型回答提交正向/负向反馈，供检索质量评估与生成审核）。"""

from __future__ import annotations

import enum
from dataclasses import dataclass


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
