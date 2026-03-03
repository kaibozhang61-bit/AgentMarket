"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Play, Plus } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { agentsApi } from "@/lib/api";
import { useAuth } from "@/contexts/auth-context";
import type { Agent } from "@/lib/types";

export default function DashboardPage() {
  const { user } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    agentsApi
      .listMine()
      .then((r) => setAgents(r.agents))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">
            Welcome back{user?.username ? `, ${user.username}` : ""}
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Here&apos;s an overview of your agents.
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[
            { label: "My Agents", value: agents.length, icon: Bot },
            {
              label: "Published",
              value: agents.filter((a) => a.status === "published").length,
              icon: Play,
            },
            {
              label: "Total Calls",
              value: agents.reduce((s, a) => s + a.callCount, 0),
              icon: Bot,
            },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-xl border bg-white p-4">
              <div className="flex items-center gap-2 text-neutral-500">
                <Icon className="h-4 w-4" />
                <span className="text-sm">{label}</span>
              </div>
              <p className="mt-2 text-2xl font-semibold">
                {loading ? "—" : value}
              </p>
            </div>
          ))}
        </div>

        {/* Quick actions */}
        <div className="flex gap-3">
          <Link
            href="/agents/new"
            className="flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            <Plus className="h-4 w-4" />
            Create Agent
          </Link>
        </div>

        {/* Recent agents */}
        <div>
          <h2 className="mb-3 text-base font-medium">Recent Agents</h2>
          {loading ? (
            <p className="text-sm text-neutral-400">Loading…</p>
          ) : agents.length === 0 ? (
            <p className="text-sm text-neutral-400">No agents yet.</p>
          ) : (
            <div className="space-y-2">
              {agents.slice(0, 5).map((a) => (
                <Link
                  key={a.agentId}
                  href={`/agents/${a.agentId}/edit`}
                  className="flex items-center justify-between rounded-lg border bg-white px-4 py-3 hover:bg-neutral-50"
                >
                  <div>
                    <p className="text-sm font-medium">{a.name}</p>
                    <p className="text-xs text-neutral-400">
                      {a.steps.length} step{a.steps.length !== 1 ? "s" : ""} · {a.callCount} calls
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      a.status === "published"
                        ? "bg-green-50 text-green-700"
                        : "bg-neutral-100 text-neutral-600"
                    }`}
                  >
                    {a.status}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
