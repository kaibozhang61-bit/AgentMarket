"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Play, Plus, Trash2 } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { runsApi, workflowsApi } from "@/lib/api";
import type { Workflow } from "@/lib/types";

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);

  function load() {
    workflowsApi
      .listMine()
      .then((r) => setWorkflows(r.workflows))
      .catch(console.error)
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleDelete(workflowId: string) {
    if (!confirm("Delete this workflow?")) return;
    await workflowsApi.delete(workflowId);
    setWorkflows((prev) => prev.filter((w) => w.workflowId !== workflowId));
  }

  async function handleRun(workflowId: string) {
    setRunning(workflowId);
    try {
      const run = await runsApi.trigger(workflowId);
      window.location.href = `/workflows/${workflowId}/runs/${run.runId}`;
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to start run");
      setRunning(null);
    }
  }

  return (
    <AppLayout>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Workflows</h1>
          <Link
            href="/workflows/new"
            className="flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            <Plus className="h-4 w-4" />
            New Workflow
          </Link>
        </div>

        {loading ? (
          <p className="text-sm text-neutral-400">Loading…</p>
        ) : workflows.length === 0 ? (
          <div className="rounded-xl border bg-white p-10 text-center text-neutral-400">
            No workflows yet.{" "}
            <Link href="/workflows/new" className="underline hover:text-neutral-700">
              Create one
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            {workflows.map((wf) => (
              <div
                key={wf.workflowId}
                className="flex items-center justify-between rounded-lg border bg-white px-4 py-3"
              >
                <Link href={`/workflows/${wf.workflowId}`} className="flex-1">
                  <p className="font-medium hover:underline">{wf.name}</p>
                  <p className="text-sm text-neutral-400">
                    {wf.steps.length} step{wf.steps.length !== 1 ? "s" : ""} ·{" "}
                    {wf.status}
                  </p>
                </Link>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleRun(wf.workflowId)}
                    disabled={running === wf.workflowId}
                    className="flex items-center gap-1.5 rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                  >
                    <Play className="h-3 w-3" />
                    {running === wf.workflowId ? "Starting…" : "Run"}
                  </button>
                  <button
                    onClick={() => handleDelete(wf.workflowId)}
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
