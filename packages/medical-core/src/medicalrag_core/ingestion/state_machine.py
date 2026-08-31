"""摄取运行（Ingestion Run）九阶段状态机（单向递进；ADR 0013 异步执行，ADR 0063 / ADR 0073 分阶段异步作业）。

摄取阶段顺序固定：accepted → extracting → extracted → chunking → enriching →
embedding → indexing → validating → published。每个阶段均为独立的异步作业，具备独立的
持久化检查点记录，支持从最后一个已持久化的阶段断点续跑；阶段重试依托 `UNIQUE(ingestion_run_id, stage)`
保证幂等性。重试次数耗尽后 Run 转移至 FAILED 终止态（供操作员排查与手动重放，ADR 0063）。

依据规范与发布门禁（发布前必须完成校验复核与索引入库），包含 validating 阶段共计 9 个阶段。
本模块为状态机合法迁移路径的唯一权威定义。
"""

from __future__ import annotations

import enum


class IngestionRunState(enum.StrEnum):
    """摄取运行所处的执行阶段枚举；FAILED 为失败终止态。"""

    ACCEPTED = "accepted"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CHUNKING = "chunking"
    ENRICHING = "enriching"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    VALIDATING = "validating"
    PUBLISHED = "published"
    FAILED = "failed"


_NEXT: dict[IngestionRunState, IngestionRunState] = {
    IngestionRunState.ACCEPTED: IngestionRunState.EXTRACTING,
    IngestionRunState.EXTRACTING: IngestionRunState.EXTRACTED,
    IngestionRunState.EXTRACTED: IngestionRunState.CHUNKING,
    IngestionRunState.CHUNKING: IngestionRunState.ENRICHING,
    IngestionRunState.ENRICHING: IngestionRunState.EMBEDDING,
    IngestionRunState.EMBEDDING: IngestionRunState.INDEXING,
    IngestionRunState.INDEXING: IngestionRunState.VALIDATING,
    IngestionRunState.VALIDATING: IngestionRunState.PUBLISHED,
}

_TERMINAL = frozenset({IngestionRunState.PUBLISHED, IngestionRunState.FAILED})


class InvalidIngestionTransition(ValueError):
    """当尝试对终止态（PUBLISHED 或 FAILED）执行非法状态推进时抛出该异常。"""


def advance(state: IngestionRunState) -> IngestionRunState:
    """计算下一摄取阶段；对于已处于 PUBLISHED 或 FAILED 终止态的 Run，推进时抛出 InvalidIngestionTransition。

    状态机单向递进：不提供回退路径，重试操作统一从最后一个已落库阶段恢复续跑。
    """
    if state in _TERMINAL:
        raise InvalidIngestionTransition(state)
    return _NEXT[state]


def is_terminal(state: IngestionRunState) -> bool:
    """判定给定状态是否为终止态（PUBLISHED 成功发布态或 FAILED 失败态）。"""
    return state in _TERMINAL
