import { createFileRoute } from "@tanstack/react-router";
import { KnowledgeDocumentsScreen } from "../../screens/admin/KnowledgeDocumentsScreen";

export const Route = createFileRoute("/admin/knowledge/$kbId/")({
  component: KnowledgeDocumentsScreen,
});
