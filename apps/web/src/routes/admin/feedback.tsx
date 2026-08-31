import { createFileRoute } from "@tanstack/react-router";
import { FeedbackScreen } from "../../screens/admin/FeedbackScreen";

export const Route = createFileRoute("/admin/feedback")({
  component: FeedbackScreen,
});
