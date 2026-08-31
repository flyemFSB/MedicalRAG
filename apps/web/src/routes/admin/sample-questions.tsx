import { createFileRoute } from "@tanstack/react-router";
import { SampleQuestionsScreen } from "../../screens/admin/SampleQuestionsScreen";

export const Route = createFileRoute("/admin/sample-questions")({
  component: SampleQuestionsScreen,
});
