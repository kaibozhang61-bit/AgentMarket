"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Pencil, X } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { SchemaEditor } from "@/components/agents/schema-editor";
import { TestPanel } from "@/components/agents/test-panel";
import { agentsApi } from "@/lib/api";
import type { Agent, AgentUpdateRequest, FieldSchema } from "@/lib/types";

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const [editVisibility, setEditVisibility] = useState<"public" | "private">(
    "private",
  );
  const [editInputSchema, setEditInputSchema] = useState<FieldSchema[]>([]);
  const [editOutputSchema, setEditOutputSchema] = useState<FieldSchema[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    agentsApi
      .get(agentId)
      .then((a) => {
        setAgent(a);
        populateEditForm(a);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  function populateEditForm(a: Agent) {
    setEditName(a.name);
    setEditDesc(a.description ?? "");
    setEditPrompt(a.systemPrompt ?? "");
    setEditVisibility(a.visibility);
    setEditInputSchema(a.inputSchema);
    setEditOutputSchema(a.outputSchema);
  }

  async function handlePublish() {
    if (!agent) return;
    setPublishing(true);
    try {
      const updated = await agentsApi.publish(agentId);
      setAgent(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const data: AgentUpdateRequest = {
        name: editName,
        description: editDesc,
        systemPrompt: editPrompt,
        visibility: editVisibility,
        inputSchema: editInputSchema.filter((f) => f.fieldName),
        outputSchema: editOutputSchema.filter((f) => f.fieldName),
      };
      const updated = await agentsApi.update(agentId, data);
      setAgent(updated);
      setEditing(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function startEditing() {
    if (agent) populateEditForm(agent);
    setEditing(true);
  }

  if (loading)
    return (
      <AppLayout>
        <p className="text-neutral-400">Loading…</p>
      </AppLayout>
    );
  if (!agent)
    return (
      <AppLayout>
        <p className="text-red-500">{error || "Not found"}</p>
      </AppLayout>
    );

  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{agent.name}</h1>
            <p className="mt-1 text-sm text-neutral-500">{agent.description}</p>
          </div>
          <div className="flex gap-2">
            {agent.status === "draft" && (
              <button
                onClick={handlePublish}
                disabled={publishing}
                className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {publishing ? "Publishing…" : "Publish"}
              </button>
            )}
            <button
              onClick={editing ? () => setEditing(false) : startEditing}
              className="flex items-center gap-1.5 rounded-md border px-4 py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50"
            >
              {editing ? (
                <>
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </>
              ) : (
                <>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </>
              )}
            </button>
          </div>
        </div>

        {error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
            {error}
          </p>
        )}

        {/* ── View mode ── */}
        {!editing && (
          <>
            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: "Status", value: agent.status },
                { label: "Visibility", value: agent.visibility },
                { label: "Call count", value: agent.callCount.toLocaleString() },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-xl border bg-white p-4">
                  <p className="text-xs text-neutral-400">{label}</p>
                  <p className="mt-1 font-medium capitalize">{value}</p>
                </div>
              ))}
            </div>

            {/* Schemas (read-only) */}
            {[
              { title: "Input Schema", fields: agent.inputSchema },
              { title: "Output Schema", fields: agent.outputSchema },
            ].map(({ title, fields }) => (
              <div key={title} className="rounded-xl border bg-white p-5">
                <h2 className="mb-3 font-medium">{title}</h2>
                {fields.length === 0 ? (
                  <p className="text-sm text-neutral-400">None defined.</p>
                ) : (
                  <div className="space-y-1.5">
                    {fields.map((f) => (
                      <div
                        key={f.fieldName}
                        className="flex items-center gap-3 text-sm"
                      >
                        <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs">
                          {f.fieldName}
                        </code>
                        <span className="text-neutral-500">{f.type}</span>
                        {f.required && (
                          <span className="text-xs text-red-500">required</span>
                        )}
                        {f.description && (
                          <span className="text-neutral-400">
                            {f.description}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* Test panel (shared component) */}
            <div className="rounded-xl border bg-white p-5">
              <TestPanel agentId={agentId} inputSchema={agent.inputSchema} />
            </div>
          </>
        )}

        {/* ── Edit mode ── */}
        {editing && (
          <form onSubmit={handleSaveEdit} className="space-y-6">
            <section className="space-y-4 rounded-xl border bg-white p-5">
              <h2 className="font-medium">Basic Info</h2>

              <Field label="Name">
                <input
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="input"
                />
              </Field>

              <Field label="Description">
                <textarea
                  rows={2}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="input resize-none"
                />
              </Field>

              <Field label="Visibility">
                <select
                  value={editVisibility}
                  onChange={(e) =>
                    setEditVisibility(e.target.value as "public" | "private")
                  }
                  className="input"
                >
                  <option value="private">Private</option>
                  <option value="public">Public</option>
                </select>
              </Field>
            </section>

            <section className="space-y-3 rounded-xl border bg-white p-5">
              <h2 className="font-medium">System Prompt</h2>
              <textarea
                rows={6}
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                className="input resize-y"
                placeholder="You are an expert at…"
              />
            </section>

            <section className="rounded-xl border bg-white p-5">
              <SchemaEditor
                title="Input Schema"
                fields={editInputSchema}
                onChange={setEditInputSchema}
              />
            </section>

            <section className="rounded-xl border bg-white p-5">
              <SchemaEditor
                title="Output Schema"
                fields={editOutputSchema}
                onChange={setEditOutputSchema}
              />
            </section>

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={saving}
                className="rounded-md bg-neutral-900 px-5 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save Changes"}
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-md border px-5 py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </AppLayout>
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
      <label className="text-sm font-medium text-neutral-700">{label}</label>
      {children}
    </div>
  );
}
