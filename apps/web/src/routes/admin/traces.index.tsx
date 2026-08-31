import { createFileRoute } from "@tanstack/react-router";
import { TracesScreen } from "../../screens/admin/TracesScreen";

export const Route = createFileRoute("/admin/traces/")({
  component: TracesScreen,
});
