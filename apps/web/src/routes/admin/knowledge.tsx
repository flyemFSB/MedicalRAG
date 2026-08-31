import { createFileRoute, Outlet } from "@tanstack/react-router";

// 知识库模块布局：/admin/knowledge 由 knowledge.index 渲染列表，子路径渲染文档/分块。
export const Route = createFileRoute("/admin/knowledge")({
  component: KnowledgeLayout,
});

function KnowledgeLayout() {
  return <Outlet />;
}
