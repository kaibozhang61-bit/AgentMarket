"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { workflowsApi } from "@/lib/api";
import type {
  AgentStep,
  LLMStep,
  LogicStep,
  Workflow,
  WorkflowStep,
} from "@/lib/types";

interface Props {
  workflowId: string;
  step: WorkflowStep;
  onWorkflowUpdated: (wf: Workflow) => void;
  onDelete: (stepId: string) => void;
}

export function StepConfigPanel({
  workflowId,
  step,
  onWorkflowUpdated,
  onDelete,
}: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function saveStep(updates: Partial<WorkflowStep>) {
    setSaving(true);
    setError("");
    try {
      const updated = await workflowsApi.updateStep(
        workflowId,
        step.stepId,
        { ...step, ...updates } as WorkflowStep,
      );
      onWorkflowUpdated(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Step Config</h3>
        <button
          onClick={() => onDelete(step.stepId)}
          className="text-neutral-300 hover:text-red-500"
          title="Remove step"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {step.type === "AGENT" && (
          <AgentStepForm step={step} saving={saving} onSave={saveStep} />
        )}
        {step.type === "LLM" && (
          <LLMStepForm step={step} saving={saving} onSave={saveStep} />
        )}
        {step.type === "LOGIC" && (
          <LogicStepForm step={step} saving={saving} onSave={saveStep} />
        )}
        {error && (
          <p className="mt-3 rounded bg-red-50 px-3 py-2 text-xs text-red-600">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium uppercase tracking-wide text-neutral-400">
        {label}
      </label>
      {children}
    </div>
  );
}

function AgentStepForm({
  step,
  saving,
  onSave,
}: {
  step: AgentStep;
  saving: boolean;
  onSave: (u: Partial<AgentStep>) => void;
}) {
  const [agentId, setAgentId] = useState(step.agentId);
  const [agentVersion, setAgentVersion] = useState(
    step.agentVersion ?? "1.0.0",
  );
  const [transformMode, setTransformMode] = useState<"auto" | "manual">(
    step.transformMode ?? "auto",
  );

  return (
    <div className="space-y-4">
      <Field label="Agent ID">
        <input
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          className="input text-xs"
          placeholder="agent-uuid"
        />
      </Field>

      <Field label="Version">
        <input
          value={agentVersion}
          onChange={(e) => setAgentVersion(e.target.value)}
          className="input text-xs"
          placeholder="1.0.0"
        />
      </Field>

      <Field label="Transform Mode">
        <select
          value={transformMode}
          onChange={(e) =>
            setTransformMode(e.target.value as "auto" | "manual")
          }
          className="input text-xs"
        >
          <option value="auto">Auto (LLM adapts fields)</option>
          <option value="manual">Manual (field mapping)</option>
        </select>
      </Field>

      <button
        onClick={() => onSave({ agentId, agentVersion, transformMode })}
        disabled={saving}
        className="w-full rounded-md bg-neutral-900 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

function LLMStepForm({
  step,
  saving,
  onSave,
}: {
  step: LLMStep;
  saving: boolean;
  onSave: (u: Partial<LLMStep>) => void;
}) {
  const [prompt, setPrompt] = useState(step.prompt ?? "");
  const [outputField, setOutputField] = useState(
    step.outputSchema?.fieldName ?? "",
  );

  return (
    <div className="space-y-4">
      <Field label="Prompt">
        <textarea
          rows={8}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="input resize-y font-mono text-xs"
          placeholder="Summarise the following: {{step1.output.text}}"
        />
      </Field>

      <Field label="Output field name">
        <input
          value={outputField}
          onChange={(e) => setOutputField(e.target.value)}
          className="input text-xs"
          placeholder="e.g. summary"
        />
      </Field>

      <button
        onClick={() =>
          onSave({
            prompt,
            outputSchema: outputField
              ? { fieldName: outputField, type: "string", required: true }
              : undefined,
          })
        }
        disabled={saving}
        className="w-full rounded-md bg-neutral-900 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

function LogicStepForm({
  step,
  saving,
  onSave,
}: {
  step: LogicStep;
  saving: boolean;
  onSave: (u: Partial<LogicStep>) => void;
}) {
  const [logicType, setLogicType] = useState<
    "condition" | "transform" | "user_input"
  >(step.logicType);
  const [condIf, setCondIf] = useState(step.condition?.if ?? "");
  const [condThen, setCondThen] = useState(step.condition?.then ?? "");
  const [condElse, setCondElse] = useState(step.condition?.else ?? "");
  const [question, setQuestion] = useState(step.question ?? "");
  const [outputField, setOutputField] = useState(step.outputField ?? "");

  function save() {
    const updates: Partial<LogicStep> = { logicType };
    if (logicType === "condition") {
      updates.condition = { if: condIf, then: condThen, else: condElse };
    } else if (logicType === "user_input") {
      updates.question = question;
      updates.outputField = outputField;
    }
    onSave(updates);
  }

  return (
    <div className="space-y-4">
      <Field label="Logic Type">
        <select
          value={logicType}
          onChange={(e) =>
            setLogicType(e.target.value as typeof logicType)
          }
          className="input text-xs"
        >
          <option value="condition">Condition (if / then / else)</option>
          <option value="transform">Transform</option>
          <option value="user_input">Ask user for input</option>
        </select>
      </Field>

      {logicType === "condition" && (
        <>
          <Field label="If (expression)">
            <input
              value={condIf}
              onChange={(e) => setCondIf(e.target.value)}
              className="input font-mono text-xs"
              placeholder="{{step1.output.score}} > 0.8"
            />
          </Field>
          <Field label="Then (step ID)">
            <input
              value={condThen}
              onChange={(e) => setCondThen(e.target.value)}
              className="input text-xs"
              placeholder="step3"
            />
          </Field>
          <Field label="Else (step ID)">
            <input
              value={condElse}
              onChange={(e) => setCondElse(e.target.value)}
              className="input text-xs"
              placeholder="step4"
            />
          </Field>
        </>
      )}

      {logicType === "user_input" && (
        <>
          <Field label="Question">
            <textarea
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="input resize-none text-xs"
              placeholder="Please provide your email address"
            />
          </Field>
          <Field label="Output field name">
            <input
              value={outputField}
              onChange={(e) => setOutputField(e.target.value)}
              className="input text-xs"
              placeholder="user_email"
            />
          </Field>
        </>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="w-full rounded-md bg-neutral-900 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
