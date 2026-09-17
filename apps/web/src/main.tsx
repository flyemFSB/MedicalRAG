import { createRouter, RouterProvider } from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { createRoot } from "react-dom/client";
import { routeTree } from "./routeTree.gen";
import { queryClient } from "./lib/queryClient";
import "./styles/tokens.css";

// 官方 Router+Query 模式（Repo QueryClient convention）：QueryClient 进 router context，
// Wrap 挂 QueryClientProvider；defaultPreloadStaleTime=0 保证 loader 数据不被 stale 跳过。
const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreloadStaleTime: 0,
  Wrap: ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  ),
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
