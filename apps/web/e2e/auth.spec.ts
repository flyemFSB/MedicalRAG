// 认证流冒烟：注册 → 会话（/api/auth/me）→ 登出（ADR 0080 E2E 层）。
// 前置：docker compose up -d 全栈可用；每次运行用唯一邮箱避免脏数据冲突。
import { expect, test } from "@playwright/test";

const email = `e2e-${Date.now()}@example.com`;
const password = "e2e-secret-123";

test("register → me → logout 完整认证流", async ({ page }) => {
  await page.goto("/login");
  // 注册
  await page
    .getByRole("button", { name: /注册/ })
    .first()
    .click();
  await page.getByLabel(/邮箱/).fill(email);
  await page.getByLabel(/密码/).fill(password);
  await page
    .getByRole("button", { name: /注册/ })
    .last()
    .click();
  // 登录成功进入工作台（会话 cookie 已种下）
  await expect(page).not.toHaveURL(/login/, { timeout: 10_000 });
  // 会话有效
  const me = await page.request.get("/api/auth/me");
  expect(me.ok()).toBeTruthy();
  // 登出后会话失效
  await page.request.post("/api/auth/logout");
  const meAfter = await page.request.get("/api/auth/me");
  expect(meAfter.status()).toBe(401);
});

test("未认证访问工作台被重定向到登录页", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/login/, { timeout: 10_000 });
});
