"""用户侧推荐样例问题路由（GET /api/sample-questions；聊天欢迎屏使用）。

样例问题由迁移 seed 写入，v1 无运营端配置 API。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import UserCtx

router = APIRouter(prefix="/api")


class SampleQuestionPublic(BaseModel):
    """用户可见的样例问题公开字段（管理端字段如 enabled/created_at 不外泄）。"""

    id: str
    text: str


@router.get("/sample-questions")
async def list_sample_questions(ctx: UserCtx, request: Request) -> list[SampleQuestionPublic]:
    """列出当前用户工作区的启用的推荐样例问题（按创建顺序）。"""
    rows = await request.app.state.operator.sample_questions.list_for_workspace(ctx.workspace_id)
    return [SampleQuestionPublic(id=str(row["id"]), text=str(row["text"])) for row in rows]
