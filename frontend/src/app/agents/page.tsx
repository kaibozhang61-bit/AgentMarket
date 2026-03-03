"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Trash2 } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { agentsApi } from "@/lib/api";
import type { Agent } from "@/lib/types";

const STATUS_COLORS: Record<Agent["status"], string> = {
  draft: "bg-neutral-100 text-neutral-600",
  published: "bg-green-50 text-green-700",
  deprecated: "bg-red-50 text-red-600",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    agentsApi
      .listMine()
      .then((r) => setAgents(r.agents))
      .catch(console.error)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleDelete(agentId: string, isDraft: boolean) {
    if (!isDraft && !confirm("Delete this agent?")) return;
    await agentsApi.delete(agentId);
    setAgents((prev) => prev.filter((a) => a.agentId !== agentId));
  }

  const published = agents.filter((a) => a.status !== "draft");
  const drafts = agents.filter((a) => a.status === "draft");

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">My Agents</h1>
          <Link
            href="/agents/new"
            className="flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            <Plus className="h-4 w-4" />
            New Agent
          </Link>
        </div>

        {loading ? (
          <p className="text-sm text-neutral-400">Loading…</p>
        ) : agents.length === 0 ? (
          <div className="rounded-xl border bg-white p-10 text-center text-neutral-400">
            No agents yet.{" "}
            <Link href="/agents/new" className="underline hover:text-neutral-700">
              Create one
            </Link>
          </div>
        ) : (
          <>
            {/* Published agents */}
            {published.length > 0 && (
              <div className="space-y-2">
                {published.map((agent) => (
                  <AgentRow
                    key={agent.agentId}
                    agent={agent}
                    onDelete={() => handleDelete(agent.agentId, false)}
                  />
                ))}
              </div>
            )}

            {/* Drafts — collapsible section */}
            {drafts.length > 0 && (
              <details open={published.length === 0}>
                <summary className="cursor-pointer text-sm font-medium text-neutral-500 hover:text-neutral-700">
                  Drafts ({drafts.length})
                </summary>
                <div className="mt-2 space-y-2">
                  {drafts.map((agent) => (
                    <AgentRow
                      key={agent.agentId}
                      agent={agent}
                      onDelete={() => handleDelete(agent.agentId, true)}
                    />
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}

function AgentRow({
  agent,
  onDelete,
}: {
  agent: Agent;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border bg-white px-4 py-3">
      <Link
        href={`/agents/${agent.agentId}/edit`}
        className="flex-1"
      >
        <p className="font-medium hover:underline">{agent.name}</p>
        <p className="text-sm text-neutral-400 line-clamp-1">
          {agent.description || "No description"}
        </p>
      </Link>

      <div className="flex items-center gap-3">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[agent.status]}`}
        >
          {agent.status}
        </span>
        {agent.status !== "draft" && (
          <span className="text-xs text-neutral-400">
            {agent.callCount} calls
          </span>
        )}
        <button
          onClick={onDelete}
          className="text-neutral-300 hover:text-red-500"
          title={agent.status === "draft" ? "Delete draft" : "Delete agent"}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
