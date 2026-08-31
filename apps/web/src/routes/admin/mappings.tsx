import { createFileRoute } from "@tanstack/react-router";
import { MappingsScreen } from "../../screens/admin/MappingsScreen";

export const Route = createFileRoute("/admin/mappings")({
  component: MappingsScreen,
});
