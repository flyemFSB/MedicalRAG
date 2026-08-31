import { createFileRoute } from "@tanstack/react-router";
import { KnowledgeChunksScreen } from "../../screens/admin/KnowledgeChunksScreen";

export const Route = createFileRoute("/admin/knowledge/$kbId/docs/$docId")({
  component: KnowledgeChunksScreen,
});
