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

  async function handleDelete(agentId: string) {
    if (!confirm("Delete this agent?")) return;
    await agentsApi.delete(agentId);
    setAgents((prev) => prev.filter((a) => a.agentId !== agentId));
  }

  return (
    <AppLayout>
      <div className="space-y-4">
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
          <div className="space-y-2">
            {agents.map((agent) => (
              <div
                key={agent.agentId}
                className="flex items-center justify-between rounded-lg border bg-white px-4 py-3"
              >
                <Link
                  href={`/agents/${agent.agentId}`}
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
                  <span className="text-xs text-neutral-400">
                    {agent.callCount} calls
                  </span>
                  <button
                    onClick={() => handleDelete(agent.agentId)}
                    className="text-neutral-300 hover:text-red-500"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
