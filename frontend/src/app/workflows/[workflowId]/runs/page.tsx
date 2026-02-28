"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle, Clock, Loader2, XCircle } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { runsApi, workflowsApi } from "@/lib/api";
import type { RunStatus, Workflow, WorkflowRun } from "@/lib/types";

const STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  success: <CheckCircle className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
  running: <Loader2 className="h-4 w-4 animate-spin text-blue-500" />,
  waiting_user_input: <Clock className="h-4 w-4 text-amber-500" />,
};

const STATUS_LABEL: Record<RunStatus, string> = {
  success: "Success",
  failed: "Failed",
  running: "Running",
  waiting_user_input: "Waiting",
};

export default function RunsListPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      workflowsApi.get(workflowId),
      runsApi.list(workflowId),
    ])
      .then(([wf, r]) => {
        setWorkflow(wf);
        setRuns(r.runs);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workflowId]);

  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        {/* Back link */}
        <Link
          href={`/workflows/${workflowId}`}
          className="flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to editor
        </Link>

        <div>
          <h1 className="text-2xl font-semibold">
            {workflow ? `${workflow.name} — Runs` : "Run History"}
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            All execution runs for this workflow
          </p>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-neutral-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : error ? (
          <p className="text-red-500">{error}</p>
        ) : runs.length === 0 ? (
          <div className="rounded-xl border bg-white p-10 text-center text-neutral-400">
            No runs yet.{" "}
            <Link
              href={`/workflows/${workflowId}`}
              className="underline hover:text-neutral-700"
            >
              Go to editor to run
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <Link
                key={run.runId}
                href={`/workflows/${workflowId}/runs/${run.runId}`}
                className="flex items-center gap-3 rounded-lg border bg-white px-4 py-3 hover:bg-neutral-50"
              >
                {STATUS_ICON[run.status]}
                <div className="flex-1">
                  <p className="font-mono text-xs text-neutral-600">
                    {run.runId}
                  </p>
                  <p className="text-xs text-neutral-400">
                    Started {new Date(run.startedAt).toLocaleString()}
                    {run.finishedAt &&
                      ` · Finished ${new Date(run.finishedAt).toLocaleString()}`}
                  </p>
                </div>
                <span className="text-xs font-medium text-neutral-500">
                  {STATUS_LABEL[run.status]}
                </span>
                <span className="text-xs text-neutral-400">
                  {run.stepResults.length} step
                  {run.stepResults.length !== 1 ? "s" : ""}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
