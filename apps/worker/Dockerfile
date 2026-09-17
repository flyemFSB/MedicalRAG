# MedicalRAG worker 镜像（apps/worker，TaskIQ 异步作业）
# version-baseline 门禁 3：arq 与 redis-py 8.x 冲突，worker 用 TaskIQ（ADR 0073）
# 多阶段构建 + 非 root 运行（ADR 0080）；对象存储根与 api 同卷（compose objects-data）
# Python 3.12（ADR 0064 修订）
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 整仓拷贝（uv workspace：packages/* 与各 app 均是成员，ADR 0060 包边界）
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps apps
COPY scripts scripts

# 只装 worker + 其依赖（core/infra），不把其他 app 带进镜像（根项目无聚合依赖）
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package medicalrag-worker

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 非 root：固定 uid；对象存储根预建并授权（volume 挂载后属主以镜像目录为准）
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/objects \
    && chown -R appuser:appuser /data
COPY --from=builder --chown=appuser:appuser /app /app
USER appuser

WORKDIR /app

# TaskIQ worker：drives 摄取阶段作业 + outbox relay
CMD ["sh", "-c", "cd apps/worker && exec taskiq worker medicalrag_worker.worker:broker"]
