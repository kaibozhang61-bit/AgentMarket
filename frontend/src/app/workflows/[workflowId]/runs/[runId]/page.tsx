"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle, Clock, Loader2, XCircle } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { runsApi } from "@/lib/api";
import type { RunStatus, StepResult, WorkflowRun } from "@/lib/types";

const POLL_INTERVAL = 2000; // ms

export default function RunDetailPage() {
  const { workflowId, runId } = useParams<{
    workflowId: string;
    runId: string;
  }>();

  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchRun = useCallback(async () => {
    const r = await runsApi.get(workflowId, runId);
    setRun(r);
    return r;
  }, [workflowId, runId]);

  useEffect(() => {
    fetchRun().finally(() => setLoading(false));
  }, [fetchRun]);

  // Poll while running
  useEffect(() => {
    if (!run) return;
    const terminal = ["success", "failed", "waiting_user_input"];
    if (terminal.includes(run.status)) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(fetchRun, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [run, fetchRun]);

  async function handleResume(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const updated = await runsApi.resume(workflowId, runId, answer);
      setRun(updated);
      setAnswer("");
      // Restart polling
      intervalRef.current = setInterval(fetchRun, POLL_INTERVAL);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Resume failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <AppLayout><p className="text-neutral-400">Loading…</p></AppLayout>;
  if (!run) return <AppLayout><p className="text-red-500">Run not found.</p></AppLayout>;

  const pendingStep = run.stepResults.find(
    (s) => s.status === "waiting_user_input",
  );

  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Run Detail</h1>
            <p className="mt-1 font-mono text-xs text-neutral-400">{runId}</p>
          </div>
          <RunStatusBadge status={run.status} />
        </div>

        {/* Timing */}
        <div className="flex gap-4 text-sm text-neutral-500">
          <span>Started: {new Date(run.startedAt).toLocaleString()}</span>
          {run.finishedAt && (
            <span>Finished: {new Date(run.finishedAt).toLocaleString()}</span>
          )}
        </div>

        {/* User input form */}
        {run.status === "waiting_user_input" && pendingStep && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 space-y-3">
            <p className="font-medium text-amber-800">Input required</p>
            <p className="text-sm text-amber-700">
              {pendingStep.pendingQuestion ?? "Please provide a value to continue."}
            </p>
            <form onSubmit={handleResume} className="flex gap-2">
              <input
                required
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Your answer…"
                className="flex-1 rounded-md border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-amber-500"
              />
              <button
                type="submit"
                disabled={submitting}
                className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {submitting ? "Submitting…" : "Continue"}
              </button>
            </form>
          </div>
        )}

        {/* Step results */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-neutral-500">
            STEPS ({run.stepResults.length})
          </h2>

          {run.stepResults.map((step, i) => (
            <StepCard key={step.stepId} step={step} index={i} />
          ))}

          {run.status === "running" && (
            <div className="flex items-center gap-2 rounded-lg border bg-white px-4 py-3 text-sm text-neutral-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Executing…
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}

function RunStatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { cls: string; label: string }> = {
    running: { cls: "bg-blue-50 text-blue-700", label: "Running" },
    success: { cls: "bg-green-50 text-green-700", label: "Success" },
    failed: { cls: "bg-red-50 text-red-600", label: "Failed" },
    waiting_user_input: { cls: "bg-amber-50 text-amber-700", label: "Waiting" },
  };
  const { cls, label } = map[status] ?? map.running;
  return (
    <span className={`rounded-full px-3 py-1 text-sm font-medium ${cls}`}>
      {label}
    </span>
  );
}

function StepCard({ step, index }: { step: StepResult; index: number }) {
  const [expanded, setExpanded] = useState(false);

  const icon =
    step.status === "success" ? (
      <CheckCircle className="h-4 w-4 text-green-500" />
    ) : step.status === "failed" ? (
      <XCircle className="h-4 w-4 text-red-500" />
    ) : step.status === "waiting_user_input" ? (
      <Clock className="h-4 w-4 text-amber-500" />
    ) : (
      <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
    );

  return (
    <div className="rounded-lg border bg-white">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-100 text-xs font-medium">
          {index + 1}
        </span>
        {icon}
        <span className="flex-1 text-sm font-medium">{step.stepId}</span>
        <span className="text-xs text-neutral-400">{step.type}</span>
        {step.latency_ms > 0 && (
          <span className="text-xs text-neutral-400">{step.latency_ms}ms</span>
        )}
        <span className="text-xs text-neutral-400">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="border-t px-4 py-3 space-y-3 text-sm">
          {step.error && (
            <p className="text-red-500">Error: {step.error}</p>
          )}
          {Object.keys(step.input).length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-neutral-400">INPUT</p>
              <pre className="rounded bg-neutral-50 p-2 text-xs overflow-x-auto">
                {JSON.stringify(step.input, null, 2)}
              </pre>
            </div>
          )}
          {Object.keys(step.output).length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-neutral-400">OUTPUT</p>
              <pre className="rounded bg-neutral-50 p-2 text-xs overflow-x-auto">
                {JSON.stringify(step.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
