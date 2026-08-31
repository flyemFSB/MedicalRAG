import { defineConfig, devices } from "@playwright/test";

// E2E 冒烟（ADR 0080）：针对 compose 全栈（docker compose up -d 后运行）。
// 前置：pnpm --filter @medicalrag/web exec playwright install chromium
// 运行：pnpm --filter @medicalrag/web test:e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
