"use client";

import { useParams } from "next/navigation";
import { redirect } from "next/navigation";

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  redirect(`/agents/${agentId}/edit`);
}
