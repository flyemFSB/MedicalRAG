import { createFileRoute } from "@tanstack/react-router";
import { IngestionScreen } from "../../screens/admin/IngestionScreen";

export const Route = createFileRoute("/admin/ingestion")({
  component: IngestionScreen,
});
