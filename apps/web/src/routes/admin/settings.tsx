import { createFileRoute } from "@tanstack/react-router";
import { SettingsScreen } from "../../screens/admin/SettingsScreen";

export const Route = createFileRoute("/admin/settings")({
  component: SettingsScreen,
});
