"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Loader2, Pencil, Play, Plus, Trash2, X } from "lucide-react";
import { agentsApi, marketplaceApi } from "@/lib/api";
import type { FieldSchema, MarketplaceAgent, WorkflowStep } from "@/lib/types";

interface Props {
  step: WorkflowStep | null;
  agentId?: string;
  isLastStep?: boolean;
  onStepUpdated?: (updated: WorkflowStep) => void;
}

export function StepDetailPanel({ step, agentId, isLastStep, onStepUpdated }: Props) {
  if (!step) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-center text-sm text-neutral-400">
          Select a step to view details
        </p>
      </div>
    );
  }

  const t = step.type.toLowerCase();
  if (t === "llm") return <LLMStepDetail step={step} agentId={agentId} isLastStep={isLastStep} onStepUpdated={onStepUpdated} />;
  if (t === "agent") return <AgentStepDetail step={step} />;
  return <p className="p-6 text-sm text-neutral-400">Unknown step type</p>;
}

// ── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, badge, children }: { title: string; badge?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-neutral-100 bg-white p-3">
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">{title}</h4>
        {badge}
      </div>
      {children}
    </div>
  );
}

// ── LLM Step Detail ──────────────────────────────────────────────────────────

function LLMStepDetail({
  step,
  agentId,
  isLastStep,
  onStepUpdated,
}: {
  step: WorkflowStep;
  agentId?: string;
  isLastStep?: boolean;
  onStepUpdated?: (updated: WorkflowStep) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editPrompt, setEditPrompt] = useState(step.systemPrompt ?? step.prompt ?? "");
  const [editInputSchema, setEditInputSchema] = useState<FieldSchema[]>(parseSchemaFields(step.inputSchema));
  const [editOutputSchema, setEditOutputSchema] = useState<FieldSchema[]>(parseSchemaFields(step.outputSchema));
  const [testInput, setTestInput] = useState("{}");
  const [testOutput, setTestOutput] = useState<string | null>(null);
  const [testLatency, setTestLatency] = useState<number | null>(null);
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState("");

  useEffect(() => {
    setEditPrompt(step.systemPrompt ?? step.prompt ?? "");
    setEditInputSchema(parseSchemaFields(step.inputSchema));
    setEditOutputSchema(parseSchemaFields(step.outputSchema));
    setEditing(false);
    setTestOutput(null);
    setTestError("");
  }, [step.stepId, step.systemPrompt, step.prompt, step.inputSchema, step.outputSchema]);

  function handleSave() {
    if (onStepUpdated) {
      onStepUpdated({
        ...step,
        systemPrompt: editPrompt,
        prompt: editPrompt,
        inputSchema: editInputSchema as unknown as Record<string, unknown>[],
        outputSchema: editOutputSchema as unknown as Record<string, unknown>,
      });
    }
    setEditing(false);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-neutral-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-100 text-xs font-bold text-purple-700">
            {step.order}
          </span>
          <div>
            <h3 className="text-sm font-semibold text-neutral-800">LLM Step</h3>
          </div>
        </div>
        <button
          onClick={() => setEditing(!editing)}
          className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium text-neutral-600 hover:bg-white"
        >
          {editing ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
          {editing ? "Cancel" : "Edit"}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* System Prompt */}
        <Section title="System Prompt">
          {editing ? (
            <textarea
              rows={8}
              value={editPrompt}
              onChange={(e) => setEditPrompt(e.target.value)}
              className="w-full resize-y rounded-md border bg-neutral-50 px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:ring-2 focus:ring-neutral-900"
            />
          ) : (
            <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md bg-neutral-50 p-3 text-xs leading-relaxed text-neutral-700">
              {step.systemPrompt ?? step.prompt ?? "No prompt defined"}
            </pre>
          )}
        </Section>

        {/* Input Schema */}
        <Section title="Input Schema">
          {editing ? (
            <SchemaFieldEditor fields={editInputSchema} onChange={setEditInputSchema} />
          ) : (
            <SchemaFieldList fields={parseSchemaFields(step.inputSchema)} emptyText="No input fields defined" />
          )}
        </Section>

        {/* Reads from Blackboard */}
        {(step.readFromBlackboard ?? []).length > 0 && (
          <Section title="Reads from Blackboard">
            <div className="space-y-1">
              {(step.readFromBlackboard ?? []).map((ref) => (
                <div key={ref} className="flex items-center gap-1.5 rounded-md bg-blue-50 px-2 py-1 text-xs">
                  <span className="text-blue-400">{"\u2190"}</span>
                  <code className="text-blue-700">{ref}</code>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Output Schema */}
        <Section title="Output Schema">
          {editing ? (
            <SchemaFieldEditor fields={editOutputSchema} onChange={setEditOutputSchema} />
          ) : (
            <SchemaFieldList fields={parseSchemaFields(step.outputSchema)} emptyText="No output fields defined" showVisibility />
          )}
        </Section>

        {/* Save button */}
        {editing && (
          <button
            onClick={handleSave}
            className="w-full rounded-md bg-neutral-900 py-2.5 text-xs font-medium text-white hover:bg-neutral-700"
          >
            Save Changes
          </button>
        )}

        {/* Test Step */}
        {agentId && !editing && (
          <Section
            title="Test Step"
            badge={testLatency !== null ? <span className="text-xs text-neutral-400">{testLatency}ms</span> : undefined}
          >
            <textarea
              rows={3}
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              spellCheck={false}
              placeholder='{"topic": "AI"}'
              className="w-full resize-y rounded-md border bg-neutral-50 px-3 py-2 font-mono text-xs outline-none focus:ring-1 focus:ring-neutral-900"
            />
            <button
              onClick={async () => {
                setTesting(true);
                setTestError("");
                setTestOutput(null);
                try {
                  const parsed = JSON.parse(testInput);
                  const res = await agentsApi.testStep(agentId, { stepId: step.stepId, input: parsed });
                  setTestOutput(JSON.stringify(res.output, null, 2));
                  setTestLatency(res.latency_ms);
                } catch (e: unknown) {
                  setTestError(e instanceof Error ? e.message : "Test failed");
                } finally {
                  setTesting(false);
                }
              }}
              disabled={testing}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md bg-neutral-900 py-2 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {testing ? "Running…" : "Run Test"}
            </button>
            {testError && (
              <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-600">{testError}</p>
            )}
            {testOutput && (
              <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-neutral-900 p-3 text-xs leading-relaxed text-green-400">
                {testOutput}
              </pre>
            )}
          </Section>
        )}
      </div>
    </div>
  );
}

// ── Agent Step Detail ────────────────────────────────────────────────────────

function AgentStepDetail({ step }: { step: WorkflowStep }) {
  const [refAgent, setRefAgent] = useState<MarketplaceAgent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!step.agentId) { setLoading(false); return; }
    setLoading(true);
    marketplaceApi.get(step.agentId)
      .then(setRefAgent)
      .catch(() => setRefAgent(null))
      .finally(() => setLoading(false));
  }, [step.agentId]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b bg-neutral-50 px-4 py-3">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">
          {step.order}
        </span>
        <h3 className="text-sm font-semibold text-neutral-800">Marketplace Agent</h3>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <p className="text-xs text-neutral-400">Loading…</p>
        ) : refAgent ? (
          <>
            <Section title="Agent Info">
              <p className="text-sm font-medium text-neutral-800">{refAgent.name}</p>
              <p className="mt-1 text-xs leading-relaxed text-neutral-500">{refAgent.description}</p>
              <Link
                href={`/marketplace/${refAgent.agentId}`}
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View in Marketplace
              </Link>
            </Section>

            {refAgent.inputSchema.length > 0 && (
              <Section title="Input Schema">
                <SchemaFieldList fields={refAgent.inputSchema} emptyText="" />
              </Section>
            )}

            {refAgent.outputSchema.length > 0 && (
              <Section title="Output Schema">
                <SchemaFieldList fields={refAgent.outputSchema} emptyText="" />
              </Section>
            )}
          </>
        ) : (
          <div className="rounded-md bg-red-50 p-3">
            <p className="text-xs text-red-600">Agent not found: {step.agentId}</p>
          </div>
        )}

        {/* Similar Agents placeholder */}
        <Section title="Similar Agents">
          <div className="rounded-lg border-2 border-dashed border-neutral-200 p-4 text-center">
            <p className="text-xs text-neutral-400">Coming soon</p>
            <p className="mt-1 text-xs text-neutral-300">
              We&apos;ll suggest alternative agents you can swap in
            </p>
          </div>
        </Section>
      </div>
    </div>
  );
}

// ── Shared schema components ─────────────────────────────────────────────────

function parseSchemaFields(schema: unknown): FieldSchema[] {
  if (!schema) return [];
  if (Array.isArray(schema)) {
    return schema.map((f) => ({
      fieldName: (f as Record<string, unknown>).fieldName as string ?? "",
      type: (f as Record<string, unknown>).type as string ?? "string",
      required: (f as Record<string, unknown>).required as boolean ?? true,
      description: (f as Record<string, unknown>).description as string ?? "",
    }));
  }
  if (typeof schema === "object") {
    const s = schema as Record<string, unknown>;
    if (s.fieldName) return [{ fieldName: s.fieldName as string, type: s.type as string ?? "string", required: true, description: s.description as string ?? "" }];
  }
  return [];
}

function SchemaFieldList({ fields, emptyText, showVisibility }: { fields: FieldSchema[]; emptyText: string; showVisibility?: boolean }) {
  if (fields.length === 0) return emptyText ? <p className="text-xs text-neutral-400">{emptyText}</p> : null;
  return (
    <div className="space-y-1.5">
      {fields.map((f, i) => (
        <div key={i} className="flex items-start gap-2 rounded-md bg-neutral-50 px-2.5 py-1.5">
          {showVisibility && (
            <span className="shrink-0 pt-0.5" title={f.visibility === "public" ? "Public" : "Private"}>
              {f.visibility === "public" ? "\uD83C\uDF10" : "\uD83D\uDD12"}
            </span>
          )}
          <code className="shrink-0 rounded bg-neutral-200/60 px-1.5 py-0.5 text-xs font-medium text-neutral-700">
            {f.fieldName}
          </code>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-neutral-500">{f.type}</span>
              {f.required && (
                <span className="rounded bg-red-50 px-1 py-0.5 text-xs text-red-500">required</span>
              )}
            </div>
            {f.description && (
              <p className="mt-0.5 text-xs leading-snug text-neutral-400">{f.description}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

const TYPES = ["string", "number", "boolean", "list<string>", "object"];

function SchemaFieldEditor({ fields, onChange }: { fields: FieldSchema[]; onChange: (f: FieldSchema[]) => void }) {
  function update(i: number, key: keyof FieldSchema, val: unknown) {
    onChange(fields.map((f, j) => (j === i ? { ...f, [key]: val } : f)));
  }
  return (
    <div className="space-y-2">
      {fields.map((f, i) => (
        <div key={i} className="flex items-start gap-1.5 rounded-md border border-neutral-100 bg-neutral-50 p-2">
          <input
            placeholder="field"
            value={f.fieldName}
            onChange={(e) => update(i, "fieldName", e.target.value)}
            className="w-20 rounded border bg-white px-1.5 py-1 text-xs outline-none focus:ring-1 focus:ring-neutral-900"
          />
          <select
            value={f.type}
            onChange={(e) => update(i, "type", e.target.value)}
            className="w-20 rounded border bg-white px-1 py-1 text-xs outline-none"
          >
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            placeholder="description"
            value={f.description ?? ""}
            onChange={(e) => update(i, "description", e.target.value)}
            className="flex-1 rounded border bg-white px-1.5 py-1 text-xs outline-none focus:ring-1 focus:ring-neutral-900"
          />
          <button onClick={() => onChange(fields.filter((_, j) => j !== i))} className="pt-1 text-neutral-300 hover:text-red-500">
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      ))}
      <button
        onClick={() => onChange([...fields, { fieldName: "", type: "string", required: true, description: "" }])}
        className="flex items-center gap-1 rounded-md border border-dashed border-neutral-300 px-2.5 py-1.5 text-xs text-neutral-500 hover:border-neutral-400 hover:text-neutral-700"
      >
        <Plus className="h-3 w-3" /> Add field
      </button>
    </div>
  );
}
