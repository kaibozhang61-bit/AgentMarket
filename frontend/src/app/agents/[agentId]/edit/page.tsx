"use client";

import { useParams } from "next/navigation";
import { AgentEditor } from "@/components/agents/agent-editor";

export default function EditAgentPage() {
  const { agentId } = useParams<{ agentId: string }>();
  return <AgentEditor agentId={agentId} />;
}
