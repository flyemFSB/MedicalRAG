import { createFileRoute } from "@tanstack/react-router";
import { IntentTreeScreen } from "../../screens/admin/IntentTreeScreen";

export const Route = createFileRoute("/admin/intents")({
  component: IntentTreeScreen,
});
