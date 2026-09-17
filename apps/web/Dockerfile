# MedicalRAG web 镜像（Vite SPA 构建 → Nginx 静态服务，ADR 0070）。
FROM node:24.18-bookworm-slim AS build
WORKDIR /app
# pnpm-workspace.yaml 含 supply-chain 政策（minimumReleaseAgeExclude），须在 install 前就位。
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# 成员 manifest 必须在内层 install 前就位：否则该层缓存失效，且 apps/web/node_modules 可能未建立
COPY apps/web/package.json apps/web/
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm --filter @medicalrag/web run build

# nginx stable line 钉 exact 版本（禁浮动 tag；升级时随 version-baseline §5 手动 bump）。
# unprivileged 变体：以 uid 101 非 root 运行并监听 8080（ADR 0080 非 root 承诺，与
# api/agent/worker 的 uid 10001 非 root 姿态一致；无需 useradd/chown 特殊处理）。
FROM nginxinc/nginx-unprivileged:1.30.4-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
