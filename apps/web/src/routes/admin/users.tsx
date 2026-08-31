import { createFileRoute } from "@tanstack/react-router";
import { UsersScreen } from "../../screens/admin/UsersScreen";

export const Route = createFileRoute("/admin/users")({
  component: UsersScreen,
});
