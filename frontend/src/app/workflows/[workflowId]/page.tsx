"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { CheckCircle, Loader2, Play, Plus, XCircle } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { StepCanvas } from "@/components/workflows/step-canvas";
import { StepConfigPanel } from "@/components/workflows/step-config-panel";
import { runsApi, workflowsApi } from "@/lib/api";
import type { ValidationIssue, Workflow, WorkflowStep } from "@/lib/types";

type NewStepType = "AGENT" | "LLM" | "LOGIC";

export default function WorkflowEditorPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<{
    compatible: boolean;
    issues: ValidationIssue[];
  } | null>(null);
  const [error, setError] = useState("");

  // Add-step modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newType, setNewType] = useState<NewStepType>("LLM");
  const [newPrompt, setNewPrompt] = useState("");
  const [newAgentId, setNewAgentId] = useState("");
  const [addingStep, setAddingStep] = useState(false);

  useEffect(() => {
    workflowsApi
      .get(workflowId)
      .then((wf) => {
        setWorkflow(wf);
        const sorted = [...wf.steps].sort((a, b) => a.order - b.order);
        if (sorted.length > 0) setSelectedStepId(sorted[0].stepId);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workflowId]);

  async function handleRun() {
    setRunning(true);
    try {
      const run = await runsApi.trigger(workflowId);
      router.push(`/workflows/${workflowId}/runs/${run.runId}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start run");
      setRunning(false);
    }
  }

  async function handleValidate() {
    setValidating(true);
    try {
      const result = await workflowsApi.validate(workflowId);
      setValidation(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  async function handleDeleteStep(stepId: string) {
    try {
      const updated = await workflowsApi.deleteStep(workflowId, stepId);
      setWorkflow(updated);
      if (selectedStepId === stepId) {
        const remaining = [...updated.steps].sort((a, b) => a.order - b.order);
        setSelectedStepId(remaining.length > 0 ? remaining[0].stepId : null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function handleAddStep(e: React.FormEvent) {
    e.preventDefault();
    if (!workflow) return;
    setAddingStep(true);
    try {
      const nextOrder = workflow.steps.length + 1;
      let stepBody: Omit<WorkflowStep, "stepId">;
      if (newType === "LLM") {
        stepBody = { type: "LLM", order: nextOrder, prompt: newPrompt };
      } else if (newType === "AGENT") {
        stepBody = { type: "AGENT", order: nextOrder, agentId: newAgentId };
      } else {
        stepBody = { type: "LOGIC", order: nextOrder, logicType: "condition" };
      }
      const updated = await workflowsApi.addStep(workflowId, stepBody);
      setWorkflow(updated);
      const sorted = [...updated.steps].sort((a, b) => a.order - b.order);
      const newStep = sorted[sorted.length - 1];
      if (newStep) setSelectedStepId(newStep.stepId);
      setShowAddModal(false);
      setNewPrompt("");
      setNewAgentId("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add step");
    } finally {
      setAddingStep(false);
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center gap-2 text-neutral-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </AppLayout>
    );
  }

  if (!workflow) {
    return (
      <AppLayout>
        <p className="text-red-500">{error || "Workflow not found."}</p>
      </AppLayout>
    );
  }

  const sortedSteps = [...workflow.steps].sort((a, b) => a.order - b.order);
  const selectedStep =
    sortedSteps.find((s) => s.stepId === selectedStepId) ?? null;

  return (
    <AppLayout>
      {/* Full-height container inside the layout */}
      <div className="flex h-[calc(100vh-4rem)] flex-col -mx-6 -my-6">
        {/* ── Top bar ────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b bg-white px-6 py-3">
          <div>
            <h1 className="text-base font-semibold">{workflow.name}</h1>
            {workflow.description && (
              <p className="text-xs text-neutral-500">{workflow.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Validation badge */}
            {validation && (
              <span className="flex items-center gap-1 text-xs">
                {validation.compatible ? (
                  <>
                    <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                    <span className="text-green-600">Compatible</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-3.5 w-3.5 text-red-500" />
                    <span className="text-red-600">
                      {validation.issues.length} issue
                      {validation.issues.length !== 1 ? "s" : ""}
                    </span>
                  </>
                )}
              </span>
            )}
            <button
              onClick={handleValidate}
              disabled={validating}
              className="rounded-md border px-3 py-1.5 text-xs font-medium text-neutral-600 hover:bg-neutral-50 disabled:opacity-50"
            >
              {validating ? "Checking…" : "Validate"}
            </button>
            <Link
              href={`/workflows/${workflowId}/runs`}
              className="rounded-md border px-3 py-1.5 text-xs font-medium text-neutral-600 hover:bg-neutral-50"
            >
              Run history
            </Link>
            <button
              onClick={handleRun}
              disabled={running || workflow.steps.length === 0}
              className="flex items-center gap-1.5 rounded-md bg-neutral-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {running ? "Starting…" : "Run"}
            </button>
          </div>
        </div>

        {/* Error bar */}
        {error && (
          <div className="border-b bg-red-50 px-6 py-2 text-xs text-red-600">
            {error}
          </div>
        )}

        {/* Validation issues bar */}
        {validation && !validation.compatible && (
          <div className="border-b bg-amber-50 px-6 py-2">
            <ul className="space-y-1">
              {validation.issues.map((issue, i) => (
                <li key={i} className="text-xs text-amber-700">
                  <span className="font-mono">{issue.stepId}</span> ·{" "}
                  <span className="font-mono">{issue.field}</span> —{" "}
                  {issue.issue}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── 3-panel body ─────────────────────────────────────────────── */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: step list */}
          <div className="flex w-52 flex-col border-r bg-white">
            <div className="border-b px-3 py-2">
              <span className="text-xs font-medium text-neutral-400">
                STEPS ({sortedSteps.length})
              </span>
            </div>

            <div className="flex-1 overflow-y-auto py-1">
              {sortedSteps.map((step, i) => (
                <button
                  key={step.stepId}
                  onClick={() => setSelectedStepId(step.stepId)}
                  className={`flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors ${
                    selectedStepId === step.stepId
                      ? "bg-neutral-100"
                      : "hover:bg-neutral-50"
                  }`}
                >
                  <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-neutral-200 text-xs font-bold text-neutral-600">
                    {i + 1}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                      step.type === "AGENT"
                        ? "bg-blue-50 text-blue-700"
                        : step.type === "LLM"
                          ? "bg-purple-50 text-purple-700"
                          : "bg-yellow-50 text-yellow-700"
                    }`}
                  >
                    {step.type}
                  </span>
                </button>
              ))}
            </div>

            <div className="border-t p-2">
              <button
                onClick={() => setShowAddModal(true)}
                className="flex w-full items-center justify-center gap-1.5 rounded-md border-2 border-dashed py-2 text-xs text-neutral-400 hover:border-neutral-400 hover:text-neutral-700"
              >
                <Plus className="h-3.5 w-3.5" />
                Add Step
              </button>
            </div>
          </div>

          {/* Center: canvas */}
          <div className="flex-1 overflow-y-auto bg-neutral-50">
            <StepCanvas
              steps={workflow.steps}
              selectedId={selectedStepId}
              onSelect={setSelectedStepId}
            />
          </div>

          {/* Right: config panel */}
          <div className="w-72 border-l bg-white">
            {selectedStep ? (
              <StepConfigPanel
                workflowId={workflowId}
                step={selectedStep}
                onWorkflowUpdated={(updated) => {
                  setWorkflow(updated);
                  setValidation(null);
                }}
                onDelete={handleDeleteStep}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-4 text-center text-sm text-neutral-400">
                Select a step to configure it
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Add-step modal ─────────────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-4 font-semibold">Add Step</h3>
            <form onSubmit={handleAddStep} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-medium text-neutral-500">
                  Step Type
                </label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as NewStepType)}
                  className="input"
                >
                  <option value="LLM">LLM (built-in)</option>
                  <option value="AGENT">Agent (marketplace)</option>
                  <option value="LOGIC">Logic</option>
                </select>
              </div>

              {newType === "LLM" && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-neutral-500">
                    Prompt
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={newPrompt}
                    onChange={(e) => setNewPrompt(e.target.value)}
                    placeholder="Summarise: {{step1.output.text}}"
                    className="input resize-none"
                  />
                </div>
              )}

              {newType === "AGENT" && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-neutral-500">
                    Agent ID
                  </label>
                  <input
                    required
                    value={newAgentId}
                    onChange={(e) => setNewAgentId(e.target.value)}
                    placeholder="agent-uuid"
                    className="input"
                  />
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  disabled={addingStep}
                  className="flex-1 rounded-md bg-neutral-900 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  {addingStep ? "Adding…" : "Add"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="flex-1 rounded-md border py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
