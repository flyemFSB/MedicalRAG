import { createFileRoute } from "@tanstack/react-router";
import { DashboardScreen } from "../../screens/admin/DashboardScreen";
import { dashboardQueryOptions } from "../../lib/queries";

export const Route = createFileRoute("/admin/dashboard")({
  loader: ({ context }) => context.queryClient.ensureQueryData(dashboardQueryOptions()),
  component: DashboardScreen,
});
