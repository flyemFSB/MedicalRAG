// MedicalRAG web（Vite 8 + React 19 + TanStack Router + Tailwind v4；ADR 0070 同源代理）。
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // 聊天路由 bundle（routes chunk）超 1MB：把重量级依赖拆为独立 vendor chunk，
        // 任一依赖升级不再打爆整个路由 bundle 的用户缓存（纯缓存优化，不改行为）。
        manualChunks(id: string) {
          if (id.includes("micromark") || id.includes("mdast-util-from-markdown")) {
            return "micromark";
          }
          if (id.includes("langgraph-sdk")) return "langgraph-sdk";
          return undefined;
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      // dev：/api + /api/agent + 健康端点 代理到后端（prod 由 Nginx 同源反代，ADR 0070）
      // 目标一律用 127.0.0.1：本机 localhost 会先解析到 ::1，而后端只监听 IPv4 → 代理悬挂。
      "/api/agent": {
        // 生产前端经 Aegra Agent Protocol v2（/api/agent）；dev 由 Vite 同源代理到 Aegra。
        // 注意：必须剥掉 /api/agent 前缀 —— Aegra 路由在根（/threads/...、/runs/stream），
        // 否则 SDK 的 runs/stream 请求会被 Aegra 以 404 静默拒绝（流式发送无任何网络请求）。
        target: process.env.MEDICALRAG_AGENT_URL ?? "http://127.0.0.1:2026",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/agent/, ""),
      },
      "/api": {
        target: process.env.MEDICALRAG_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ready": {
        target: process.env.MEDICALRAG_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/healthz": {
        target: process.env.MEDICALRAG_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
