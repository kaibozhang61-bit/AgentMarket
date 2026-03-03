"use client";

import { useEffect, useState } from "react";
import { Pencil, X } from "lucide-react";
import { SchemaEditor } from "@/components/agents/schema-editor";
import type { FieldSchema } from "@/lib/types";

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
  onAgentUpdated?: (fields: {
    name?: string;
    description?: string;
    inputSchema?: FieldSchema[];
    outputSchema?: FieldSchema[];
  }) => void;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-neutral-100 bg-white p-3">
      <h4 className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-neutral-500">{title}</h4>
      {hint && <p className="mb-2 text-xs text-neutral-300">{hint}</p>}
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

export function AgentDetailPanel({ agent, onAgentUpdated }: Props) {
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
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-200 text-xs font-bold text-neutral-600">
            A
          </span>
          <h3 className="text-sm font-semibold text-neutral-800">Agent Details</h3>
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
        {/* Name */}
        <Section title="Name">
          {editing ? (
            <input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full rounded-md border px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-neutral-900"
            />
          ) : (
            <p className="text-sm font-medium text-neutral-800">{agent.name}</p>
          )}
        </Section>

        {/* Description */}
        <Section title="Description">
          {editing ? (
            <textarea
              rows={3}
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              className="w-full resize-y rounded-md border px-2.5 py-1.5 text-xs leading-relaxed outline-none focus:ring-1 focus:ring-neutral-900"
            />
          ) : (
            <p className="text-xs leading-relaxed text-neutral-600">
              {agent.description || "No description"}
            </p>
          )}
        </Section>

        {/* Status */}
        <Section title="Status">
          <span
            className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
              agent.status === "published"
                ? "bg-green-50 text-green-700"
                : "bg-neutral-100 text-neutral-600"
            }`}
          >
            {agent.status}
          </span>
        </Section>

        {/* Input Schema */}
        <Section title="Agent Input" hint="What the user provides when running this agent">
          {editing ? (
            <SchemaEditor title="" fields={editInputSchema} onChange={setEditInputSchema} />
          ) : (
            <FieldList fields={agent.inputSchema} emptyText="No input fields defined" />
          )}
        </Section>

        {/* Output Schema */}
        <Section title="Agent Output" hint="What the agent returns after execution">
          {editing ? (
            <SchemaEditor title="" fields={editOutputSchema} onChange={setEditOutputSchema} />
          ) : (
            <FieldList fields={agent.outputSchema} emptyText="No output fields defined" />
          )}
        </Section>

        {/* Save */}
        {editing && (
          <button
            onClick={handleSave}
            className="w-full rounded-md bg-neutral-900 py-2.5 text-xs font-medium text-white hover:bg-neutral-700"
          >
            Save Changes
          </button>
        )}
      </div>
    </div>
  );
}
