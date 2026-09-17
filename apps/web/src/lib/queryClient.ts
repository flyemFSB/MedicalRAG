// QueryClient（Repo QueryClient convention：staleTime 60s / retry 3 / 窗口聚焦刷新）。
import { QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api";

// 全局 401 兜底：会话过期是最常见的生产路径。任一查询收到 401（me 查询自身除外，
// 它把 401 归一为 null）即整体跳转登录页重置状态——避免「假空态/重试死循环」。
let redirecting = false;

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.status === 401 &&
        !redirecting &&
        window.location.pathname !== "/login"
      ) {
        redirecting = true;
        window.location.assign("/login");
      }
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 3,
      refetchOnWindowFocus: true,
    },
  },
});
