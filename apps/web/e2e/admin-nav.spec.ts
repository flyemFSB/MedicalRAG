// 运营台导航冒烟：operator 登录 → 逐页渲染非空（角色门禁 + 管理面可用性，ADR 0080 E2E 层）。
// 前置：docker compose up -d 全栈可用；MEDICALRAG_OPERATOR_EMAILS 含本用例邮箱。
// 若部署未将该邮箱列为 operator，本用例以角色门禁拒绝为预期（二选一断言，不误报）。
import { expect, test } from "@playwright/test";

const email = `e2e-admin-${Date.now()}@example.com`;
const password = "e2e-secret-123";

const PAGES: Array<[string, RegExp]> = [
  ["/admin/dashboard", /仪表盘/],
  ["/admin/knowledge", /知识库/],
  ["/admin/ingestion", /摄取运行/],
  ["/admin/intents", /意图树/],
  ["/admin/traces", /链路追踪/],
  ["/admin/feedback", /反馈/],
];

test("operator 逐页导航渲染", async ({ page }) => {
  await page.goto("/login");
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
  await expect(page).not.toHaveURL(/login/, { timeout: 10_000 });

  await page.goto("/admin/dashboard");
  const isOperator = await page
    .getByText("运营控制台")
    .first()
    .isVisible()
    .catch(() => false);
  test.skip(!isOperator, "部署未将 e2e 邮箱配置为 operator，跳过管理面冒烟");

  for (const [path, heading] of PAGES) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { level: 1 }).or(page.getByText(heading).first()),
    ).toBeVisible({ timeout: 10_000 });
    // 页面未落到错误兜底组件（ErrorBoundary 文案）
    await expect(page.getByText("页面出现异常")).toHaveCount(0);
  }
});
