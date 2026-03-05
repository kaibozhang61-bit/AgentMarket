"use client";

import { useState } from "react";
import { Loader2, Zap } from "lucide-react";
import type { SearchResult, MetricValue } from "@/lib/types";
import { MetricsTable } from "@/components/agents/metrics-table";
import { ExecutionForm } from "@/components/agents/execution-form";

interface Props {
  results: SearchResult[];
  metrics?: Record<string, Record<string, MetricValue>>;
  metricsLoading?: boolean;
  onSelectAgent: (agentId: string) => void;
  onRequestMetrics: (metrics: string[]) => void;
  onRunAgent: (agentId: string, input: Record<string, unknown>) => void;
  onSwitchToPathB: () => void;
  onSwitchToPathC: () => void;
}

const SUGGESTED_METRICS = [
  "success_rate",
  "discount_rate",
  "duration_ms",
  "rounds",
];

export function SearchResults({
  results,
  metrics,
  metricsLoading,
  onSelectAgent,
  onRequestMetrics,
  onRunAgent,
  onSwitchToPathB,
  onSwitchToPathC,
}: Props) {
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [showExecution, setShowExecution] = useState(false);

  function handleMetricToggle(metric: string) {
    setSelectedMetrics((prev) =>
      prev.includes(metric)
        ? prev.filter((m) => m !== metric)
        : [...prev, metric],
    );
  }

  function handleAnalyze() {
    if (selectedMetrics.length > 0) {
      onRequestMetrics(selectedMetrics);
    }
  }

  function handleSelectAgent(agentId: string) {
    setSelectedAgentId(agentId);
    setShowExecution(true);
    onSelectAgent(agentId);
  }

  if (showExecution && selectedAgentId) {
    const agent = results.find((r) => r.agent_id === selectedAgentId);
    return (
      <div className="space-y-3">
        <button
          onClick={() => setShowExecution(false)}
          className="text-xs text-neutral-500 hover:text-neutral-700"
        >
          ← Back to results
        </button>
        <ExecutionForm
          agentId={selectedAgentId}
          agentName={agent?.name ?? ""}
          onRun={(input) => onRunAgent(selectedAgentId, input)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-700">
          Found {results.length} matching agent{results.length !== 1 ? "s" : ""}
        </h3>
      </div>

      {/* Agent comparison table */}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-left text-xs" role="table">
          <thead>
            <tr className="border-b bg-neutral-50">
              <th scope="col" className="px-3 py-2 font-medium text-neutral-500">Agent</th>
              <th scope="col" className="px-3 py-2 font-medium text-neutral-500">Description</th>
              <th scope="col" className="px-3 py-2 font-medium text-neutral-500">Score</th>
              {selectedMetrics.map((m) => (
                <th key={m} scope="col" className="px-3 py-2 font-medium text-neutral-500">
                  {m.replace(/_/g, " ")}
                </th>
              ))}
              <th scope="col" className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {results.map((agent) => (
              <tr
                key={agent.agent_id}
                className="border-b last:border-0 hover:bg-neutral-50"
              >
                <td className="px-3 py-2 font-medium text-neutral-800">
                  {agent.name}
                </td>
                <td className="max-w-[200px] truncate px-3 py-2 text-neutral-600">
                  {agent.description}
                </td>
                <td className="px-3 py-2 text-neutral-600">
                  {(agent.score * 100).toFixed(0)}%
                </td>
                {selectedMetrics.map((m) => (
                  <td key={m} className="px-3 py-2">
                    <MetricsTable
                      agentId={agent.agent_id}
                      metric={m}
                      value={metrics?.[agent.agent_id]?.[m]}
                      loading={metricsLoading}
                    />
                  </td>
                ))}
                <td className="px-3 py-2">
                  <button
                    onClick={() => handleSelectAgent(agent.agent_id)}
                    className="rounded bg-neutral-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-neutral-700"
                  >
                    Select
                  </button>
                </td>
              </tr>
            ))}
            {/* Free new agent option */}
            <tr className="border-b last:border-0 bg-green-50/50">
              <td className="px-3 py-2 font-medium text-green-700">
                New Agent 🆓
              </td>
              <td className="px-3 py-2 text-green-600 text-xs">
                Create a new agent from scratch
              </td>
              <td className="px-3 py-2 text-neutral-400">—</td>
              {selectedMetrics.map((m) => (
                <td key={m} className="px-3 py-2 text-neutral-400">—</td>
              ))}
              <td className="px-3 py-2">
                <button
                  onClick={onSwitchToPathC}
                  className="rounded border border-green-600 px-2.5 py-1 text-xs font-medium text-green-700 hover:bg-green-50"
                >
                  Create
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Metrics selection */}
      <div className="rounded-lg border p-3">
        <p className="mb-2 text-xs font-medium text-neutral-500">
          Which metrics matter to you?
        </p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTED_METRICS.map((m) => (
            <button
              key={m}
              onClick={() => handleMetricToggle(m)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                selectedMetrics.includes(m)
                  ? "bg-neutral-900 text-white"
                  : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
              }`}
            >
              {m.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        {selectedMetrics.length > 0 && (
          <button
            onClick={handleAnalyze}
            disabled={metricsLoading}
            className="mt-2 flex items-center gap-1.5 rounded bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
          >
            {metricsLoading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Zap className="h-3 w-3" />
            )}
            Analyze
          </button>
        )}
      </div>

      {/* Path switching */}
      <div className="flex gap-2 text-xs">
        <button
          onClick={onSwitchToPathB}
          className="text-neutral-500 hover:text-neutral-700 underline"
        >
          None of these fit exactly
        </button>
        <span className="text-neutral-300">·</span>
        <button
          onClick={onSwitchToPathC}
          className="text-neutral-500 hover:text-neutral-700 underline"
        >
          Build from scratch
        </button>
      </div>
    </div>
  );
}
