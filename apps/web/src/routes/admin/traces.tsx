import { createFileRoute, Outlet } from "@tanstack/react-router";

// 链路追踪模块布局：/admin/traces 由 traces.index 渲染列表，子路径渲染运行详情。
export const Route = createFileRoute("/admin/traces")({
  component: TracesLayout,
});

function TracesLayout() {
  return <Outlet />;
}
