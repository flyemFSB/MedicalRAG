# MedicalRAG agent 镜像（apps/agent，Aegra 托管 LangGraph 图）
# aegra serve 不支持 Windows，本镜像仅在 Linux 构建/运行（recipe §5.6）
# version-baseline：aegra-cli 钉版；Python 3.12（ADR 0064 修订）
# aegra 启动参数以官方 compose/文档为准（Agent Protocol v2 + OTLP，ADR 0076）
# 多阶段构建 + 非 root 运行（ADR 0080）
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 整仓拷贝（uv workspace：packages/* 与各 app 均是成员，ADR 0060 包边界）
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY apps apps
COPY scripts scripts

# 只装 agent + 其依赖（core/infra/assembly），不把其他 app 带进镜像（根项目无聚合依赖）
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package medicalrag-agent

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser
COPY --from=builder --chown=appuser:appuser /app /app
USER appuser

WORKDIR /app

EXPOSE 2026

# Aegra serve 托管 aegra.json 中的 LangGraph 图（同源 /api/agent 由 Nginx 反代）
# 先跑 aegra db upgrade 建 checkpoint 表（幂等；RUN_MIGRATIONS_ON_STARTUP 实测未生效）
CMD ["sh", "-c", "cd apps/agent && aegra db upgrade && exec aegra serve -c aegra.json"]
