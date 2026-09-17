// UI 实跑验证脚本（项目门禁：改前端必须在浏览器实跑再宣称完成）。
// 用法：node scripts/verify-ui.mjs [baseUrl] —— 依赖 apps/web 已装 playwright-core，
// 驱动系统 Chrome（channel: chrome）。登录后逐个模块截图并存控制台错误。
import { chromium } from "playwright-core";
import { fileURLToPath } from "node:url";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = fileURLToPath(new URL("../.verify", import.meta.url));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(`[console.error] ${msg.text()}`);
});
page.on("pageerror", (err) => errors.push(`[pageerror] ${err.message}`));

async function shot(name) {
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
  console.log(`✓ ${name}`);
}

try {
  // 登录
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await shot("01-login");
  await page.fill('input[type="email"]', "ops@clinic.example");
  await page.fill('input[type="password"]', "password123");
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1200);

  // 聊天欢迎页
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await shot("02-chat-welcome");

  // 创建真实知识库（获得真实 uuid，供文档/分块/详情路由使用）
  const kbId = await page.evaluate(async () => {
    const resp = await fetch("/api/admin/knowledge-bases", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "验证知识库", description: "verify-ui 自动创建" }),
    });
    if (!resp.ok) return null;
    const body = await resp.json();
    return body.id;
  });
  const uuid = () => crypto.randomUUID();

  // 运营控制台各模块
  const routes = [
    ["dashboard", "/admin/dashboard"],
    ["knowledge", "/admin/knowledge"],
    ["knowledge-docs", kbId ? `/admin/knowledge/${kbId}` : "/admin/knowledge"],
    ["knowledge-chunks", kbId ? `/admin/knowledge/${kbId}/docs/${uuid()}` : "/admin/knowledge"],
    ["ingestion", "/admin/ingestion"],
    ["intents", "/admin/intents"],
    ["mappings", "/admin/mappings"],
    ["settings", "/admin/settings"],
    ["traces", "/admin/traces"],
    ["traces-detail", `/admin/traces/${uuid()}`],
    ["feedback", "/admin/feedback"],
    ["users", "/admin/users"],
    ["audit", "/admin/audit"],
  ];
  for (const [name, path] of routes) {
    await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    await shot(`03-admin-${name}`);
  }

  // 服务状态
  await page.goto(`${BASE}/status`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await shot("04-status");
} catch (err) {
  errors.push(`[flow] ${err.message}`);
}

console.log("\n=== 控制台/页面错误 ===");
console.log(errors.length ? errors.join("\n") : "（无）");
await browser.close();
process.exit(errors.length ? 1 : 0);
