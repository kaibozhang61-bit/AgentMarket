"use client";

import type { WorkflowStep } from "@/lib/types";

interface Props {
  steps: WorkflowStep[];
  selectedId: string | null;
  onSelect: (stepId: string) => void;
}

const TYPE_COLORS: Record<string, string> = {
  AGENT: "border-blue-300 bg-blue-50 text-blue-700",
  LLM: "border-purple-300 bg-purple-50 text-purple-700",
  LOGIC: "border-yellow-300 bg-yellow-50 text-yellow-700",
};

function stepSummary(step: WorkflowStep): string {
  if (step.type === "AGENT") {
    return step.agentId ? `Agent: ${step.agentId.slice(0, 24)}` : "No agent selected";
  }
  if (step.type === "LLM") {
    const p = step.prompt ?? "";
    return p.length > 50 ? p.slice(0, 50) + "…" : p || "No prompt";
  }
  return `Logic: ${step.logicType ?? "–"}`;
}

export function StepCanvas({ steps, selectedId, onSelect }: Props) {
  const sorted = [...steps].sort((a, b) => a.order - b.order);

  if (sorted.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-center text-sm text-neutral-400">
          No steps yet.
          <br />
          Add steps from the left panel.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center py-8">
      {sorted.map((step, i) => (
        <div key={step.stepId} className="flex flex-col items-center">
          {/* Step node */}
          <button
            onClick={() => onSelect(step.stepId)}
            className={`w-52 rounded-xl border-2 p-4 text-left transition-all ${
              selectedId === step.stepId
                ? "border-neutral-900 bg-white shadow-lg"
                : "border-neutral-200 bg-white hover:border-neutral-400 hover:shadow-sm"
            }`}
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-neutral-900 text-xs font-bold text-white">
                {i + 1}
              </span>
              <span
                className={`rounded border px-1.5 py-0.5 text-xs font-semibold ${TYPE_COLORS[step.type]}`}
              >
                {step.type}
              </span>
            </div>
            <p className="truncate text-xs text-neutral-500">{stepSummary(step)}</p>
          </button>

          {/* Connector arrow */}
          {i < sorted.length - 1 && (
            <div className="flex flex-col items-center">
              <div className="h-5 w-px bg-neutral-300" />
              <div className="h-0 w-0 border-l-[5px] border-r-[5px] border-t-[7px] border-l-transparent border-r-transparent border-t-neutral-300" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
