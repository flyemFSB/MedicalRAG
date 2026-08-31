import { createFileRoute } from "@tanstack/react-router";
import { TraceDetailScreen } from "../../screens/admin/TraceDetailScreen";

export const Route = createFileRoute("/admin/traces/$runId")({
  component: TraceDetailScreen,
});
