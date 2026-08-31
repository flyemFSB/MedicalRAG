# MedicalRAG web 镜像（Vite SPA 构建 → Nginx 静态服务，ADR 0070）。
FROM node:24.18-bookworm-slim AS build
WORKDIR /app
# pnpm-workspace.yaml 含 supply-chain 政策（minimumReleaseAgeExclude），须在 install 前就位。
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm --filter @medicalrag/web run build

# nginx stable line 钉 exact 版本（禁浮动 tag；升级时随 version-baseline §5 手动 bump）
FROM nginx:1.30.4-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 80
