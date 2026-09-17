"""用户反馈 API 路由（对应产品规范用户故事 18：收集点赞/点踩反馈与文本评价，供后续检索与生成质量审核）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from medicalrag_core.ids import uuid7
from medicalrag_core.records import Feedback, FeedbackValue

from ..deps import UserCtx

router = APIRouter(prefix="/api/feedback")


class FeedbackIn(BaseModel):
    message_id: str
    conversation_id: str
    value: FeedbackValue
    comment: str | None = Field(default=None, max_length=2000)


@router.post("", status_code=201)
async def submit_feedback(body: FeedbackIn, ctx: UserCtx, request: Request) -> dict[str, str]:
    """提交针对单条助手回答的用户反馈（赞同/反对及可选的文字说明）。

    必须校验会话归属：否则任意用户可对他人会话写入反馈（对象级越权写，OWASP API1）。
    """
    operator = request.app.state.operator
    if not await operator.conversations.owned_by(body.conversation_id, ctx.user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    await operator.feedback.submit(
        Feedback(
            id=str(uuid7()),
            message_id=body.message_id,
            conversation_id=body.conversation_id,
            user_id=ctx.user_id,
            workspace_id=ctx.workspace_id,
            value=body.value,
            comment=body.comment,
        )
    )
    return {"status": "ok"}
