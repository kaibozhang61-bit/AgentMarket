"use client";

import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { marketplaceApi } from "@/lib/api";
import type { FieldSchema } from "@/lib/types";

type ExecutionMode = "chat" | "form" | "hybrid";

interface Props {
  agentId: string;
  agentName: string;
  /** Pre-filled input from hybrid mode (LLM extracted fields from chat) */
  prefilled?: Record<string, unknown>;
  onRun: (input: Record<string, unknown>) => void;
}

export function ExecutionForm({ agentId, agentName, prefilled, onRun }: Props) {
  const [mode, setMode] = useState<ExecutionMode>("form");
  const [inputSchema, setInputSchema] = useState<FieldSchema[]>([]);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [jsonInput, setJsonInput] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  // Fetch agent's inputSchema
  useEffect(() => {
    marketplaceApi
      .get(agentId)
      .then((agent) => {
        setInputSchema(agent.inputSchema ?? []);
        // Initialize form values
        const initial: Record<string, string> = {};
        for (const field of agent.inputSchema ?? []) {
          const prefilledVal = prefilled?.[field.fieldName];
          initial[field.fieldName] =
            prefilledVal !== undefined ? String(prefilledVal) : String(field.default ?? "");
        }
        setFormValues(initial);
        setJsonInput(JSON.stringify(
          Object.fromEntries(
            (agent.inputSchema ?? []).map((f) => [
              f.fieldName,
              prefilled?.[f.fieldName] ?? f.default ?? "",
            ]),
          ),
          null,
          2,
        ));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [agentId, prefilled]);

  function handleFieldChange(fieldName: string, value: string) {
    setFormValues((prev) => ({ ...prev, [fieldName]: value }));
  }

  function handleRun() {
    setRunning(true);
    let input: Record<string, unknown>;
    if (mode === "form" || mode === "hybrid") {
      input = { ...formValues };
      // Try to parse numeric values
      for (const field of inputSchema) {
        if (field.type === "number" && input[field.fieldName]) {
          const num = Number(input[field.fieldName]);
          if (!isNaN(num)) input[field.fieldName] = num;
        }
        if (field.type === "boolean" && input[field.fieldName]) {
          input[field.fieldName] = input[field.fieldName] === "true";
        }
      }
    } else {
      try {
        input = JSON.parse(jsonInput);
      } catch {
        setRunning(false);
        return;
      }
    }
    onRun(input);
    setRunning(false);
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center">
        <Loader2 className="h-4 w-4 animate-spin text-neutral-400" />
        <span className="text-xs text-neutral-400">Loading agent schema…</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-neutral-800">{agentName}</h3>
        <p className="text-xs text-neutral-500">Configure input and run</p>
      </div>

      {/* Mode selector */}
      <div className="flex gap-1 rounded-lg bg-neutral-100 p-0.5" role="tablist">
        {(["form", "chat", "hybrid"] as ExecutionMode[]).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
              mode === m
                ? "bg-white text-neutral-900 shadow-sm"
                : "text-neutral-500 hover:text-neutral-700"
            }`}
          >
            {m === "form" ? "Form" : m === "chat" ? "JSON" : "Hybrid"}
          </button>
        ))}
      </div>

      {/* Form mode */}
      {(mode === "form" || mode === "hybrid") && (
        <div className="space-y-3">
          {inputSchema.map((field) => (
            <div key={field.fieldName}>
              <label
                htmlFor={`field-${field.fieldName}`}
                className="mb-1 block text-xs font-medium text-neutral-600"
              >
                {field.fieldName}
                {field.required && <span className="ml-0.5 text-red-500">*</span>}
                <span className="ml-1 text-neutral-400">({field.type})</span>
              </label>
              {field.description && (
                <p className="mb-1 text-xs text-neutral-400">{field.description}</p>
              )}
              {field.type === "boolean" ? (
                <select
                  id={`field-${field.fieldName}`}
                  value={formValues[field.fieldName] ?? ""}
                  onChange={(e) => handleFieldChange(field.fieldName, e.target.value)}
                  className="w-full rounded-md border px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-neutral-900"
                >
                  <option value="">Select…</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : (
                <input
                  id={`field-${field.fieldName}`}
                  type={field.type === "number" ? "number" : "text"}
                  value={formValues[field.fieldName] ?? ""}
                  onChange={(e) => handleFieldChange(field.fieldName, e.target.value)}
                  placeholder={field.description || field.fieldName}
                  className="w-full rounded-md border px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-neutral-900"
                />
              )}
            </div>
          ))}
          {inputSchema.length === 0 && (
            <p className="text-xs text-neutral-400">No input fields defined</p>
          )}
        </div>
      )}

      {/* JSON mode */}
      {mode === "chat" && (
        <textarea
          rows={8}
          value={jsonInput}
          onChange={(e) => setJsonInput(e.target.value)}
          spellCheck={false}
          className="w-full resize-y rounded-md border bg-neutral-50 px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-neutral-900"
        />
      )}

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={running}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-neutral-900 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
      >
        {running ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {running ? "Running…" : "Run Agent"}
      </button>
    </div>
  );
}
