"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Phone } from "lucide-react";
import { marketplaceApi } from "@/lib/api";
import type { MarketplaceAgent } from "@/lib/types";

export default function MarketplaceAgentPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<MarketplaceAgent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    marketplaceApi
      .get(agentId)
      .then(setAgent)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  if (loading) return <LoadingState />;
  if (error || !agent) return <ErrorState message={error} />;

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b bg-white px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <button
            onClick={() => router.back()}
            className="mb-3 flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-semibold">{agent.name}</h1>
              <p className="mt-0.5 text-sm text-neutral-500">
                {agent.description}
              </p>
            </div>
            <div className="flex items-center gap-1.5 rounded-full bg-neutral-100 px-3 py-1 text-sm text-neutral-600">
              <Phone className="h-3.5 w-3.5" />
              {agent.callCount.toLocaleString()} calls
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {/* Input schema */}
        <SchemaTable title="Input Schema" fields={agent.inputSchema} />

        {/* Output schema */}
        <SchemaTable title="Output Schema" fields={agent.outputSchema} />

        {/* Meta */}
        <div className="rounded-xl border bg-white p-5 text-sm text-neutral-500 space-y-1">
          <p>Version: {agent.version}</p>
          <p>Created: {new Date(agent.createdAt).toLocaleDateString()}</p>
        </div>
      </div>
    </div>
  );
}

function SchemaTable({
  title,
  fields,
}: {
  title: string;
  fields: MarketplaceAgent["inputSchema"];
}) {
  return (
    <div className="rounded-xl border bg-white p-5">
      <h2 className="mb-3 font-medium">{title}</h2>
      {fields.length === 0 ? (
        <p className="text-sm text-neutral-400">None defined.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-neutral-500">
              <th className="pb-2 pr-4 font-medium">Field</th>
              <th className="pb-2 pr-4 font-medium">Type</th>
              <th className="pb-2 pr-4 font-medium">Required</th>
              <th className="pb-2 font-medium">Description</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.fieldName} className="border-b last:border-0">
                <td className="py-2 pr-4 font-mono text-xs">{f.fieldName}</td>
                <td className="py-2 pr-4 text-neutral-500">{f.type}</td>
                <td className="py-2 pr-4">
                  {f.required ? (
                    <span className="text-red-500">Yes</span>
                  ) : (
                    <span className="text-neutral-400">No</span>
                  )}
                </td>
                <td className="py-2 text-neutral-400">
                  {f.description ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex min-h-screen items-center justify-center text-neutral-400">
      Loading…
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-red-500">{message || "Agent not found."}</p>
    </div>
  );
}
