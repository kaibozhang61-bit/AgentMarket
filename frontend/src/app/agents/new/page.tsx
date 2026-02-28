"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppLayout } from "@/components/layout/app-layout";
import { SchemaEditor } from "@/components/agents/schema-editor";
import { agentsApi } from "@/lib/api";
import type { FieldSchema } from "@/lib/types";

export default function NewAgentPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [visibility, setVisibility] = useState<"public" | "private">("private");
  const [inputSchema, setInputSchema] = useState<FieldSchema[]>([]);
  const [outputSchema, setOutputSchema] = useState<FieldSchema[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const agent = await agentsApi.create({
        name,
        description,
        systemPrompt,
        visibility,
        inputSchema: inputSchema.filter((f) => f.fieldName),
        outputSchema: outputSchema.filter((f) => f.fieldName),
      });
      router.push(`/agents/${agent.agentId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="text-2xl font-semibold">New Agent</h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic info */}
          <section className="space-y-4 rounded-xl border bg-white p-5">
            <h2 className="font-medium">Basic Info</h2>

            <Field label="Name">
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input"
                placeholder="SEO Keyword Researcher"
              />
            </Field>

            <Field label="Description">
              <textarea
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input resize-none"
                placeholder="What does this agent do?"
              />
            </Field>

            <Field label="Visibility">
              <select
                value={visibility}
                onChange={(e) =>
                  setVisibility(e.target.value as "public" | "private")
                }
                className="input"
              >
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
            </Field>
          </section>

          {/* System prompt */}
          <section className="space-y-3 rounded-xl border bg-white p-5">
            <h2 className="font-medium">System Prompt</h2>
            <textarea
              rows={6}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className="input resize-y"
              placeholder="You are an SEO expert. Given a topic, return a list of relevant keywords..."
            />
          </section>

          {/* Schemas */}
          <section className="rounded-xl border bg-white p-5">
            <SchemaEditor
              title="Input Schema"
              fields={inputSchema}
              onChange={setInputSchema}
            />
          </section>

          <section className="rounded-xl border bg-white p-5">
            <SchemaEditor
              title="Output Schema"
              fields={outputSchema}
              onChange={setOutputSchema}
            />
          </section>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </p>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-neutral-900 px-5 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create Agent"}
            </button>
            <button
              type="button"
              onClick={() => router.back()}
              className="rounded-md border px-5 py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50"
            >
              Cancel
            </button>
          </div>
        </form>
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
