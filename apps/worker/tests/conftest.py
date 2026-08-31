"""Worker 测试环境：模块导入即校验配置（生产 fail-fast 语义），测试提供内存兜底值。"""

import os

os.environ.setdefault("MEDICALRAG_DATABASE_URL", "postgresql+asyncpg://localhost:5432/test")
os.environ.setdefault("MEDICALRAG_REDIS_URL", "redis://localhost:6379/0")
