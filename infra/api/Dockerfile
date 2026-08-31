# MedicalRAG api 镜像（apps/api，FastAPI 组合根）。
# 多阶段构建：builder 装 venv，runtime 只带产物；非 root 运行（ADR 0080）。
# uv 管理 Python 3.14（ADR 0064）；包索引走阿里云（ADR 0065，根 pyproject 已配置）。
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 整仓拷贝（uv workspace：packages/* 与各 app 均是成员，ADR 0060 包边界）。
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps apps
COPY scripts scripts

RUN uv sync --frozen --no-dev

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 非 root：固定 uid；对象存储根预建并授权。
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/objects \
    && chown -R appuser:appuser /data
COPY --from=builder --chown=appuser:appuser /app /app
USER appuser

WORKDIR /app

EXPOSE 8000

# schema 迁移由 compose 的一次性 migrate 服务执行（ADR 0080），镜像只负责起服务。
CMD ["sh", "-c", "cd apps/api && uvicorn medicalrag_api.main:create_app --factory --host 0.0.0.0 --port 8000"]
