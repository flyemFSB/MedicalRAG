"""应用核心配置项定义（基于 pydantic-settings 实现；开发规范 §5：启动阶段执行 fail-fast 校验）。

环境变量统一使用 `MEDICALRAG_` 前缀；数据库连接地址为必填项（缺失则立即阻断启动）。
所有敏感凭据仅允许通过环境变量或安全密钥管理器注入，严禁硬编码至代码库中。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API 运行时全局配置项。"""

    model_config = SettingsConfigDict(env_prefix="MEDICALRAG_", env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    # ADR 0019：__Host- Cookie 必须附带 Secure 属性；本地 HTTP 开发调试可置为 False
    cookie_secure: bool = True
    # 外部大语言模型提供商配置（ADR 0009 / ADR 0010）；API 密钥通过环境变量注入
    llm_base_url: str = "https://api.openai.com"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # 外部重排模型配置（ADR 0037）：留空表示不启用外部重排（直接依据多路融合得分调序）
    rerank_model: str = ""
    # Qdrant 向量检索服务配置（ADR 0026 迁移至 Qdrant；单容器部署）
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "medical_chunks_v1"
    qdrant_embedding_dim: int = 1536
    # 证据检索控制策略（ADR 0039 版本化管理）
    retrieval_policy_version: int = 1
    retrieval_context_cap: int = 8
    # 平台管理员邮箱列表（逗号分隔）；命中邮箱在登录时自动赋予运营控制台权限
    operator_emails: str = ""
    # 速率限制配置（规范用户故事 28）：在线聊天按每用户每分钟配额限制；登录按来源 IP 防暴力破解
    chat_rate_limit: int = 30
    chat_rate_window_s: int = 60
    auth_rate_limit: int = 10
    auth_rate_window_s: int = 60
    # 本地文件系统对象存储根路径（v1 默认实现；遵循 ObjectStorage 协议端口，ADR 0075）
    object_root: str = "./objects"

    @property
    def operator_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.operator_emails.split(",") if e.strip())


def session_cookie_name(secure: bool) -> str:
    """获取会话 Cookie 名称（ADR 0019 规范）。

    __Host- 前缀强制要求 Secure 属性，仅在 HTTPS 生产环境中可用；
    本地 HTTP 开发调试环境（cookie_secure=False）使用普通名称，避免浏览器直接丢弃未加密的会话 Cookie。
    """
    return "__Host-SessionID" if secure else "MedicalRAG-SessionID"
