import { createFileRoute } from "@tanstack/react-router";
import { ChatScreen } from "../screens/ChatScreen";

export const Route = createFileRoute("/")({
  component: ChatScreen,
});
