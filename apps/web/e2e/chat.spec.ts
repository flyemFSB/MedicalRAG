// 聊天流冒烟：登录 → 新建会话 → 发送问题 → 证据/回答出现（ADR 0080 E2E 层核心缺口补齐）。
// 前置：docker compose up -d 全栈可用，且 LLM/嵌入 provider 已配置（对话走 Aegra v2）。
import { expect, test } from "@playwright/test";

const email = `e2e-chat-${Date.now()}@example.com`;
const password = "e2e-secret-123";

test.beforeEach(async ({ page }) => {
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
});

test("发送问题后收到回答（流式聊天主路径）", async ({ page }) => {
  await page.goto("/");
  // 新建会话（侧栏「新建」按钮）
  await page
    .getByRole("button", { name: /新建/ })
    .first()
    .click();
  // 在输入框发送问题（composer 文本域）
  const composer = page.getByRole("textbox").last();
  await composer.fill("高血压患者在日常饮食上需要注意什么？");
  await composer.press("Enter");
  // 回答以助手消息形态出现；免责声明横幅恒可见（ADR 0042）
  await expect(page.getByText("AI生成内容仅供参考，不可替代医嘱，请以医生诊断为准")).toBeVisible({
    timeout: 60_000,
  });
  // 等待流式回答渲染完成：助手消息操作栏（无障碍名称「复制」，隐藏于生成中）出现即回答已落地。
  // 不用 data-slot 等内部 DOM 槽位定位（ADR 0080：E2E 只面向用户可见属性）。
  await expect(page.getByRole("button", { name: "复制" })).toBeVisible({ timeout: 60_000 });
});
