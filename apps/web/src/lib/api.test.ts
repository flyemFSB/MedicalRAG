// API 请求层的 seam 测试：只钉网络边界上可被外部观察到的决策。
// 不逐个断言 snake_case → camelCase 的字段改名——那是把实现再抄一遍（同义反复）。
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchKnowledgeBases, fetchRun } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(handler: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(handler);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch 边界契约", () => {
  it("非 2xx 抛出带 HTTP 状态码的 ApiError", async () => {
    stubFetch(() => jsonResponse({ detail: "forbidden" }, 403));
    await expect(fetchKnowledgeBases()).rejects.toBeInstanceOf(ApiError);
    await expect(fetchKnowledgeBases()).rejects.toMatchObject({ status: 403 });
  });

  it("带同源 Cookie 凭据并以 JSON 提交（登录态走 Cookie，跨源会丢凭据）", async () => {
    const fetchMock = stubFetch(() => jsonResponse([]));
    await fetchKnowledgeBases();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/knowledge-bases",
      expect.objectContaining({
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
});

describe("fetchRun 的未找到语义", () => {
  it("404 返回 null（详情页据此显示未找到，而不是甩错误）", async () => {
    stubFetch(() => jsonResponse({ detail: "not found" }, 404));
    await expect(fetchRun("run-1")).resolves.toBeNull();
  });

  it("非 404 错误照抛（500 不能被吞成未找到）", async () => {
    stubFetch(() => jsonResponse({ detail: "boom" }, 500));
    await expect(fetchRun("run-1")).rejects.toMatchObject({ status: 500 });
  });
});
