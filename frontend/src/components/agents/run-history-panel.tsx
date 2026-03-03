"use client";

import { useEffect, useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, Clock, History, Loader2, XCircle } from "lucide-react";
import { agentsApi } from "@/lib/api";

interface Run {
  runId: string;
  agentId: string;
  triggeredBy: string;
  status: string;
  stepResults: StepResult[];
  blackboard?: Record<string, unknown>;
  startedAt: string;
  finishedAt: string | null;
}

interface StepResult {
  stepId: string;
  type: string;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  latency_ms: number;
  error?: string;
  validationWarnings?: string[];
}

interface Props {
  agentId: string | null;
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  success: <CheckCircle className="h-3.5 w-3.5 text-green-500" />,
  failed: <XCircle className="h-3.5 w-3.5 text-red-500" />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />,
  waiting_user_input: <Clock className="h-3.5 w-3.5 text-amber-500" />,
};

export function RunHistoryPanel({ agentId }: Props) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);

  useEffect(() => {
    if (!open || !agentId) return;
    setLoading(true);
    fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/agents/${agentId}/runs`,
      { headers: { Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}` } },
    )
      .then((r) => r.json())
      .then((data) => setRuns(data.runs ?? []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, [open, agentId]);

  if (!agentId) return null;

  return (
    <div className="absolute bottom-0 left-0 z-20 w-80">
      {/* Toggle button */}
      <button
        onClick={() => { setOpen(!open); setSelectedRun(null); }}
        className="flex items-center gap-2 rounded-tr-lg border-r border-t bg-white px-3 py-2 text-xs font-medium text-neutral-600 shadow-sm hover:bg-neutral-50"
      >
        <History className="h-3.5 w-3.5" />
        Run History
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
      </button>

      {/* Panel */}
      {open && (
        <div className="max-h-80 overflow-y-auto border-r border-t bg-white shadow-lg">
          {selectedRun ? (
            <RunDetail run={selectedRun} onBack={() => setSelectedRun(null)} />
          ) : (
            <RunList runs={runs} loading={loading} onSelect={setSelectedRun} />
          )}
        </div>
      )}
    </div>
  );
}

function RunList({ runs, loading, onSelect }: { runs: Run[]; loading: boolean; onSelect: (r: Run) => void }) {
  if (loading) {
    return <p className="p-4 text-xs text-neutral-400">Loading...</p>;
  }
  if (runs.length === 0) {
    return <p className="p-4 text-xs text-neutral-400">No runs yet. Click &quot;Test Run&quot; to start one.</p>;
  }
  return (
    <div className="divide-y">
      {runs.map((run) => (
        <button
          key={run.runId}
          onClick={() => onSelect(run)}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-neutral-50"
        >
          {STATUS_ICON[run.status] ?? STATUS_ICON.running}
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-xs text-neutral-600">{run.runId.slice(0, 12)}...</p>
            <p className="text-xs text-neutral-400">
              {new Date(run.startedAt).toLocaleString()}
              {run.finishedAt && ` \u2022 ${run.stepResults.length} steps`}
            </p>
          </div>
          <span className="shrink-0 text-xs text-neutral-400">{run.status}</span>
        </button>
      ))}
    </div>
  );
}

function RunDetail({ run, onBack }: { run: Run; onBack: () => void }) {
  const [expandedStep, setExpandedStep] = useState<string | null>(null);
  const bb = (run.blackboard ?? {}) as Record<string, Record<string, unknown>>;

  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-xs text-blue-600 hover:text-blue-800">
          &larr; Back to list
        </button>
        <div className="flex items-center gap-1.5">
          {STATUS_ICON[run.status] ?? STATUS_ICON.running}
          <span className="text-xs font-medium">{run.status}</span>
        </div>
      </div>

      <p className="font-mono text-xs text-neutral-500">{run.runId}</p>

      {/* Step results */}
      <div className="space-y-1">
        <p className="text-xs font-semibold text-neutral-500">Steps</p>
        {run.stepResults.map((sr) => (
          <div key={sr.stepId} className="rounded-md border bg-neutral-50">
            <button
              onClick={() => setExpandedStep(expandedStep === sr.stepId ? null : sr.stepId)}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
            >
              {STATUS_ICON[sr.status] ?? STATUS_ICON.running}
              <span className="flex-1 truncate text-xs font-medium text-neutral-700">
                {sr.stepId.slice(0, 12)}
              </span>
              <span className="text-xs text-neutral-400">{sr.type}</span>
              {sr.latency_ms > 0 && <span className="text-xs text-neutral-300">{sr.latency_ms}ms</span>}
            </button>
            {expandedStep === sr.stepId && (
              <div className="border-t px-2.5 py-2 space-y-2 text-xs">
                {sr.error && <p className="text-red-500">Error: {sr.error}</p>}
                {Object.keys(sr.input).length > 0 && (
                  <div>
                    <p className="font-medium text-neutral-400">Input</p>
                    <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-neutral-100 p-1.5 text-xs">
                      {JSON.stringify(sr.input, null, 2)}
                    </pre>
                  </div>
                )}
                {Object.keys(sr.output).length > 0 && (
                  <div>
                    <p className="font-medium text-neutral-400">Output</p>
                    <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-neutral-900 p-1.5 text-xs text-green-400">
                      {JSON.stringify(sr.output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Blackboard state */}
      {Object.keys(bb).length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-neutral-500">Blackboard</p>
          {Object.entries(bb).map(([key, entry]) => {
            const val = (entry as Record<string, unknown>)?.value;
            const writtenAt = (entry as Record<string, unknown>)?.writtenAt as string;
            return (
              <div key={key} className="rounded-md border border-amber-200 bg-amber-50/50 px-2.5 py-1.5">
                <div className="flex items-center justify-between">
                  <code className="text-xs font-medium text-amber-800">{key}</code>
                  {writtenAt && (
                    <span className="text-xs text-amber-400">
                      {new Date(writtenAt).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                {val && (
                  <pre className="mt-1 max-h-20 overflow-auto rounded bg-white p-1.5 text-xs text-neutral-600">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
