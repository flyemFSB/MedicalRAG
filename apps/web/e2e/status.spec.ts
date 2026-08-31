// 健康面冒烟：/healthz 与 /ready 同源反代可达（compose web → api）。
import { expect, test } from "@playwright/test";

test("健康探针经同源反代可达", async ({ request }) => {
  const healthz = await request.get("/healthz");
  expect(healthz.ok()).toBeTruthy();
  const ready = await request.get("/ready");
  expect(ready.ok()).toBeTruthy();
});

test("Prometheus /metrics 端点暴露文本格式", async ({ request }) => {
  const resp = await request.get("/api/metrics");
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body).toHaveProperty("counters");
});
