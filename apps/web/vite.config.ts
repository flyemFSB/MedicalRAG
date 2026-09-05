// MedicalRAG web（Vite 8 + React 19 + TanStack Router + Tailwind v4；ADR 0070 同源代理）。
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      // dev：/api + /api/agent + 健康端点 代理到后端（prod 由 Nginx 同源反代，ADR 0070）
      "/api/agent": {
        // 生产前端经 Aegra Agent Protocol v2（/api/agent）；dev 由 Vite 同源代理到 Aegra。
        target: process.env.MEDICALRAG_AGENT_URL ?? "http://localhost:2026",
        changeOrigin: true,
      },
      "/api": {
        target: process.env.MEDICALRAG_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/ready": {
        target: process.env.MEDICALRAG_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/healthz": {
        target: process.env.MEDICALRAG_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
