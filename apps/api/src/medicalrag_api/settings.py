"""应用核心配置项定义（基于 pydantic-settings 实现；字段约束在构造期即执行 fail-fast 校验）。

环境变量统一使用 `MEDICALRAG_` 前缀；数据库连接地址为必填项（缺失则立即阻断启动）。
所有敏感凭据仅允许通过环境变量或安全密钥管理器注入，严禁硬编码至代码库中。
生产聊天经由 Aegra 运行时（apps/agent）装配模型与检索 Provider，本服务不持有相关配置。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from medicalrag_infra.auth.sessions import session_cookie_name

__all__ = ["Settings", "session_cookie_name"]


class Settings(BaseSettings):
    """API 运行时全局配置项。"""

    model_config = SettingsConfigDict(env_prefix="MEDICALRAG_", env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    # __Host- Cookie 必须附带 Secure 属性；本地 HTTP 开发调试可置为 False
    cookie_secure: bool = True
    # Qdrant 向量检索服务地址（/ready 就绪探针检测其连通性；检索本身由 apps/agent 承担）
    qdrant_url: str = "http://localhost:6333"
    # 平台管理员邮箱列表（逗号分隔）；命中邮箱在登录时自动赋予运营控制台权限
    operator_emails: str = ""
    # 速率限制配置（规范用户故事 28）：登录按来源 IP 防暴力破解
    auth_rate_limit: int = Field(default=10, ge=1)
    auth_rate_window_s: int = Field(default=60, ge=1)
    # 本地文件系统对象存储根路径（v1 默认实现；遵循 ObjectStorage 协议端口）
    object_root: str = "./objects"

    @property
    def operator_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.operator_emails.split(",") if e.strip())
