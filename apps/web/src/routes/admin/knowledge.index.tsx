import { createFileRoute } from "@tanstack/react-router";
import { KnowledgeListScreen } from "../../screens/admin/KnowledgeListScreen";

export const Route = createFileRoute("/admin/knowledge/")({
  component: KnowledgeListScreen,
});
