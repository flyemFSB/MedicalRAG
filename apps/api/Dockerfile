# MedicalRAG api 镜像（apps/api，FastAPI 组合根）
# 多阶段构建：builder 装 venv，runtime 只带产物；非 root 运行（ADR 0080）
# uv 管理 Python 3.12（ADR 0064 修订）；包索引走阿里云（ADR 0065，根 pyproject 已配置）
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 整仓拷贝（uv workspace：packages/* 与各 app 均是成员，ADR 0060 包边界）
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps apps
COPY scripts scripts

# 只装 api + 其依赖（core/infra/assembly），不把其他 app 带进镜像（根项目无聚合依赖）
# cache mount：uv 下载缓存不落入镜像层，重建时不再重新下载全部 wheel（UV_LINK_MODE=copy 是配套要求）
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package medicalrag-api

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 非 root：固定 uid；对象存储根预建并授权
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/objects \
    && chown -R appuser:appuser /data
COPY --from=builder --chown=appuser:appuser /app /app
USER appuser

WORKDIR /app

EXPOSE 8000

# schema 迁移由 compose 的一次性 migrate 服务执行（ADR 0080），镜像只负责起服务
# exec：shell 形式带复合命令时不会转发信号，容器 PID 1 变 sh 导致 SIGTERM 收不到（优雅停机失效）
CMD ["sh", "-c", "cd apps/api && exec uvicorn medicalrag_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
