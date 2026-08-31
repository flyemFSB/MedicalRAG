import { createFileRoute, Outlet } from "@tanstack/react-router";

// 知识库文档布局：/admin/knowledge/$kbId 由 knowledge.$kbId.index 渲染文档列表，
// 子路径 /docs/$docId 渲染分块管理。
export const Route = createFileRoute("/admin/knowledge/$kbId")({
  component: KnowledgeDocsLayout,
});

function KnowledgeDocsLayout() {
  return <Outlet />;
}
