import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import http from "node:http";

const ARTIFACT_DIR =
  "C:/Users/Administrator/.gemini/antigravity/brain/75f3968a-5b22-4d6c-be4f-d74b9a634fca";
const PORT = 4173;
const BASE_URL = `http://127.0.0.1:${PORT}`;

// 1. 启动 vite preview
console.log("Starting vite preview...");
const previewProc = spawn(
  "pnpm",
  ["exec", "vite", "preview", "--port", String(PORT), "--host", "127.0.0.1"],
  {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    shell: true,
    stdio: "inherit",
  },
);

function cleanup() {
  try {
    if (previewProc.pid) {
      spawn("taskkill", ["/pid", String(previewProc.pid), "/t", "/f"], { shell: true });
    }
  } catch {}
  try {
    previewProc.kill();
  } catch {}
}

process.on("exit", cleanup);
process.on("SIGINT", () => {
  cleanup();
  process.exit();
});
process.on("SIGTERM", () => {
  cleanup();
  process.exit();
});

// 等待端口就绪
async function waitForServer(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(url, (res) => {
          if (res.statusCode && res.statusCode < 500) resolve(true);
          else reject(new Error(`Status ${res.statusCode}`));
        });
        req.on("error", reject);
        req.setTimeout(1000, () => req.destroy());
      });
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 400));
    }
  }
  throw new Error("Server timeout");
}

try {
  await waitForServer(BASE_URL);
  console.log("Server ready at", BASE_URL);

  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // 高清 2x 渲染
  });
  const page = await context.newPage();

  // 设置统一的 API mock 响应
  await page.route("**/api/auth/me", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ email: "dr.lin@clinical.example", role: "operator" }),
    });
  });

  await page.route("**/api/conversations", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "conv-1",
          title: "高血压联合用药指南与循证禁忌",
          updated_at: new Date(Date.now() - 15 * 60000).toISOString(),
        },
        {
          id: "conv-2",
          title: "二型糖尿病一线用药肾功能评估",
          updated_at: new Date(Date.now() - 120 * 60000).toISOString(),
        },
        {
          id: "conv-3",
          title: "阿司匹林肠溶片服药时机与黏膜保护",
          updated_at: new Date(Date.now() - 1440 * 60000).toISOString(),
        },
        {
          id: "conv-4",
          title: "成人社区获得性肺炎经验性抗菌治疗",
          updated_at: new Date(Date.now() - 2880 * 60000).toISOString(),
        },
      ]),
    });
  });

  await page.route("**/api/sample-questions", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { id: "q-1", text: "高血压伴冠心病患者的首选降压药推荐及禁忌？" },
        { id: "q-2", text: "二甲双胍在 eGFR 低于多少时需要减量或停用？" },
        { id: "q-3", text: "成人社区获得性肺炎初始抗感染治疗指南方案？" },
        { id: "q-4", text: "他汀类降脂药引起的肌痛需要监测哪些指标？" },
      ]),
    });
  });

  await page.route("**/ready", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "healthy",
        checks: {
          "PostgreSQL 16 (Primary Database)": "healthy",
          "Redis 7 (Session & Cache)": "healthy",
          "Qdrant (Vector Engine)": "healthy",
          "TaskIQ (Outbox & Workers)": "healthy",
          "MinerU (Document Ingestion Engine)": "healthy",
        },
      }),
    });
  });

  await page.route("**/api/admin/dashboard", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total_chats: 1428,
        total_questions: 3892,
        avg_latency_ms: 840,
        published_docs: 156,
        failed_runs: 0,
        active_model_targets: 3,
        degraded_model_targets: 0,
      }),
    });
  });

  await page.route("**/api/admin/knowledge-bases", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "kb-1",
          name: "心血管临床诊疗指南与专家共识库",
          description: "收录中国高血压防治指南、冠心病二级预防等国家级循证医学指南",
          document_count: 42,
          created_at: "2026-03-01T08:00:00Z",
          updated_at: "2026-09-12T10:30:00Z",
        },
        {
          id: "kb-2",
          name: "内分泌与代谢性疾病循证规范",
          description: "二型糖尿病一线用药、甲状腺疾病、高尿酸血症规范化评估与方案",
          document_count: 38,
          created_at: "2026-04-15T08:00:00Z",
          updated_at: "2026-09-10T14:20:00Z",
        },
        {
          id: "kb-3",
          name: "成人呼吸系统感染合理用药指南",
          description: "社区获得性肺炎（CAP）、医院获得性肺炎抗菌药物经验性选药原则",
          document_count: 29,
          created_at: "2026-05-20T08:00:00Z",
          updated_at: "2026-09-08T09:15:00Z",
        },
        {
          id: "kb-4",
          name: "国家基本药物与处方集说明书库",
          description: "权威药品说明书、配伍禁忌、特殊人群（肝肾功能不全）剂量调整方案",
          document_count: 47,
          created_at: "2026-01-10T08:00:00Z",
          updated_at: "2026-09-14T02:00:00Z",
        },
      ]),
    });
  });

  // 1. 聊天工作台截图
  console.log("Capturing 01-chat-workbench.png...");
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/01-chat-workbench.png`, fullPage: false });

  // 2. 运营控制台仪表盘截图
  console.log("Capturing 02-admin-dashboard.png...");
  await page.goto(`${BASE_URL}/admin/dashboard`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/02-admin-dashboard.png`, fullPage: false });

  // 3. 运营控制台知识库表格截图（Many Islands Inset Table 风格）
  console.log("Capturing 05-admin-knowledge-table.png...");
  await page.goto(`${BASE_URL}/admin/knowledge`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/05-admin-knowledge-table.png`, fullPage: false });

  // 4. 服务状态页截图（Many Islands 单一工作岛）
  console.log("Capturing 03-status-island.png...");
  await page.goto(`${BASE_URL}/status`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/03-status-island.png`, fullPage: false });

  // 5. 登录页截图（未登录）
  console.log("Capturing 04-login-screen.png...");
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401, body: "" }));
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/04-login-screen.png`, fullPage: false });

  await browser.close();
  console.log("All screenshots captured successfully!");
} finally {
  cleanup();
}
