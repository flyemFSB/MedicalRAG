// QueryClient（implementation-recipes §3.2：staleTime 60s / retry 3 / 窗口聚焦刷新）。
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 3,
      refetchOnWindowFocus: true,
    },
  },
});
