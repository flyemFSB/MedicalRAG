import { createFileRoute } from "@tanstack/react-router";

// 知识库模块布局：/admin/knowledge 由 knowledge.index 渲染列表，子路径渲染文档/分块。
// 缺省 component 即渲染 <Outlet />。
export const Route = createFileRoute("/admin/knowledge")({});
