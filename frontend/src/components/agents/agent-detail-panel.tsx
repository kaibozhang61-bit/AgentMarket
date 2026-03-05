"use client";

import { useEffect, useState } from "react";
import { Globe, Lock, Pencil, X } from "lucide-react";
import { SchemaEditor } from "@/components/agents/schema-editor";
import type { FieldSchema } from "@/lib/types";

interface StepOutputGroup {
  stepId: string;
  label: string;
  fields: FieldSchema[];
}

interface Props {
  agent: {
    name: string;
    description: string;
    status: string;
    inputSchema: FieldSchema[];
    outputSchema: FieldSchema[];
    context: Record<string, string>;
    callCount: number;
    lastUsedAt: string | null;
  };
  stepOutputGroups: StepOutputGroup[];
  onAgentUpdated?: (fields: {
    name?: string;
    description?: string;
    inputSchema?: FieldSchema[];
    outputSchema?: FieldSchema[];
  }) => void;
  onVisibilityChanged?: (stepId: string, fieldName: string, visibility: "public" | "private") => void;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-neutral-100 bg-white p-3">
      <h4 className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-neutral-500">{title}</h4>
      {hint && <p className="mb-2 text-xs leading-relaxed text-neutral-400">{hint}</p>}
      {children}
    </div>
  );
}

function FieldList({ fields, emptyText }: { fields: FieldSchema[]; emptyText: string }) {
  if (fields.length === 0) return <p className="text-xs text-neutral-400">{emptyText}</p>;
  return (
    <div className="space-y-1.5">
      {fields.map((f, i) => (
        <div key={i} className="flex items-start gap-2 rounded-md bg-neutral-50 px-2.5 py-1.5">
          <code className="shrink-0 rounded bg-neutral-200/60 px-1.5 py-0.5 text-xs font-medium text-neutral-700">{f.fieldName}</code>
          <div className="min-w-0 flex-1">
            <span className="text-xs text-neutral-500">{f.type}</span>
            {f.required && <span className="ml-1.5 rounded bg-red-50 px-1 py-0.5 text-xs text-red-500">required</span>}
            {f.description && <p className="mt-0.5 text-xs leading-snug text-neutral-400">{f.description}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function AgentDetailPanel({ agent, stepOutputGroups, onAgentUpdated, onVisibilityChanged }: Props) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(agent.name);
  const [editDesc, setEditDesc] = useState(agent.description);
  const [editInputSchema, setEditInputSchema] = useState<FieldSchema[]>(agent.inputSchema);
  const [editOutputSchema, setEditOutputSchema] = useState<FieldSchema[]>(agent.outputSchema);

  useEffect(() => {
    setEditName(agent.name);
    setEditDesc(agent.description);
    setEditInputSchema(agent.inputSchema);
    setEditOutputSchema(agent.outputSchema);
    setEditing(false);
  }, [agent.name, agent.description, agent.inputSchema, agent.outputSchema]);

  function handleSave() {
    if (onAgentUpdated) {
      onAgentUpdated({
        name: editName,
        description: editDesc,
        inputSchema: editInputSchema.filter((f) => f.fieldName),
        outputSchema: editOutputSchema.filter((f) => f.fieldName),
      });
    }
    setEditing(false);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-neutral-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-200 text-xs font-bold text-neutral-600">A</span>
          <h3 className="text-sm font-semibold text-neutral-800">Agent &amp; Blackboard</h3>
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
        {/* Name & Description */}
        <Section title="Agent">
          {editing ? (
            <div className="space-y-2">
              <input value={editName} onChange={(e) => setEditName(e.target.value)}
                className="w-full rounded-md border px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-neutral-900" placeholder="Agent name" />
              <textarea rows={2} value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                className="w-full resize-y rounded-md border px-2.5 py-1.5 text-xs outline-none focus:ring-1 focus:ring-neutral-900" placeholder="Description" />
            </div>
          ) : (
            <div>
              <p className="text-sm font-medium text-neutral-800">{agent.name}</p>
              <p className="mt-1 text-xs leading-relaxed text-neutral-600">{agent.description || "No description"}</p>
              <span className={`mt-2 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                agent.status === "published" ? "bg-green-50 text-green-700" : "bg-neutral-100 text-neutral-600"
              }`}>{agent.status}</span>
            </div>
          )}
        </Section>

        {/* Agent Input */}
        <Section title="Agent Input" hint="What the user provides when running this agent. These fields are written to the blackboard as agent_input at the start of execution.">
          {editing ? (
            <SchemaEditor title="" fields={editInputSchema} onChange={setEditInputSchema} />
          ) : (
            <FieldList fields={agent.inputSchema} emptyText="No input fields defined" />
          )}
        </Section>

        {/* Agent Output */}
        <Section title="Agent Output" hint="What the agent returns after all steps complete. This is the final result delivered to the caller.">
          {editing ? (
            <SchemaEditor title="" fields={editOutputSchema} onChange={setEditOutputSchema} />
          ) : (
            <FieldList fields={agent.outputSchema} emptyText="No output fields defined" />
          )}
        </Section>

        {editing && (
          <button onClick={handleSave}
            className="w-full rounded-md bg-neutral-900 py-2.5 text-xs font-medium text-white hover:bg-neutral-700">
            Save Changes
          </button>
        )}

        {/* Blackboard explanation */}
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-amber-500 text-xs font-bold text-white">B</span>
            <h4 className="text-xs font-semibold text-amber-800">Blackboard</h4>
          </div>
          <p className="text-xs leading-relaxed text-amber-700">
            The blackboard is a shared memory space for your agent. When the agent runs,
            the user&apos;s input is written to the blackboard first. Then each step reads
            what it needs from the blackboard, does its work, and writes its output back.
            This way, later steps can use results from earlier steps.
          </p>
        </div>

        {/* Step output visibility toggles */}
        {stepOutputGroups.length > 0 && (
          <Section
            title="Step Output Visibility"
            hint="Control which step outputs are visible when other agents use this agent as a step. Public fields can be read by outer agents. Private fields are internal only."
          >
            <div className="mb-3 flex gap-4 text-xs">
              <div className="flex items-center gap-1.5">
                <Globe className="h-3 w-3 text-blue-500" />
                <span className="text-neutral-600">Public — visible to outer agents</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Lock className="h-3 w-3 text-neutral-400" />
                <span className="text-neutral-600">Private — internal only</span>
              </div>
            </div>

            <div className="space-y-3">
              {stepOutputGroups.map((g) => (
                <div key={g.stepId}>
                  <p className="mb-1.5 text-xs font-semibold text-amber-600">{g.label}</p>
                  <div className="space-y-1">
                    {g.fields.map((f) => (
                      <div key={f.fieldName} className="flex items-center justify-between rounded-md bg-neutral-50 px-2.5 py-1.5">
                        <div className="flex items-center gap-2">
                          <code className="rounded bg-neutral-200/60 px-1.5 py-0.5 text-xs font-medium text-neutral-700">{f.fieldName}</code>
                          <span className="text-xs text-neutral-400">{f.type}</span>
                        </div>
                        <button
                          onClick={() => {
                            const newVis = f.visibility === "public" ? "private" : "public";
                            if (onVisibilityChanged) onVisibilityChanged(g.stepId, f.fieldName, newVis);
                          }}
                          className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium transition-colors ${
                            f.visibility === "public"
                              ? "bg-blue-50 text-blue-600 hover:bg-blue-100"
                              : "bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
                          }`}
                        >
                          {f.visibility === "public" ? <Globe className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
                          {f.visibility === "public" ? "Public" : "Private"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
