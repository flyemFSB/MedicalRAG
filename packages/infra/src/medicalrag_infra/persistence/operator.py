"""运营管理后台仓储聚合门面（自 operator.py 拆分后仅保留组装；具体仓储见同包领域模块）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conversation_repos import (
    SqlConversationRepository,
    SqlFeedbackRepository,
    SqlRunListingRepository,
)
from .identity_repos import (
    SqlAdminUserRepository,
    SqlMembershipRepository,
    SqlWorkspaceRepository,
)
from .ingestion import SqlIngestionRunRepository
from .knowledge_repos import (
    SqlChunkRepository,
    SqlDocumentRepository,
    SqlIngestionRunListing,
    SqlKnowledgeBaseRepository,
)
from .ops_repos import (
    SqlModelTargetRepository,
    SqlOutboxRepository,
    SqlQueryTermMappingRepository,
    SqlSampleQuestionRepository,
)


class OperatorRepositories:
    """运营管理后台仓储聚合门面（供 API 服务组合根进行依赖注入装配）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.workspaces = SqlWorkspaceRepository(sessions)
        self.memberships = SqlMembershipRepository(sessions)
        self.knowledge_bases = SqlKnowledgeBaseRepository(sessions)
        self.documents = SqlDocumentRepository(sessions)
        self.chunks = SqlChunkRepository(sessions)
        self.feedback = SqlFeedbackRepository(sessions)
        self.conversations = SqlConversationRepository(sessions)
        self.model_targets = SqlModelTargetRepository(sessions)
        self.outbox = SqlOutboxRepository(sessions)
        self.runs = SqlRunListingRepository(sessions)
        self.mappings = SqlQueryTermMappingRepository(sessions)
        self.users = SqlAdminUserRepository(sessions)
        self.sample_questions = SqlSampleQuestionRepository(sessions)
        self.ingestion_runs = SqlIngestionRunListing(sessions)
        self.ingestion = SqlIngestionRunRepository(sessions)
