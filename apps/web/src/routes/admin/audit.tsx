import { createFileRoute } from "@tanstack/react-router";
import { AuditScreen } from "../../screens/admin/AuditScreen";

export const Route = createFileRoute("/admin/audit")({
  component: AuditScreen,
});
