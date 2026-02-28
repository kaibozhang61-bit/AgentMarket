"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { marketplaceApi } from "@/lib/api";
import type { MarketplaceAgent } from "@/lib/types";

export default function MarketplacePage() {
  const [agents, setAgents] = useState<MarketplaceAgent[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const req = query.trim()
      ? marketplaceApi.search(query.trim(), { page })
      : marketplaceApi.list({ page });
    req
      .then((r) => {
        setAgents(r.agents);
        setTotal(r.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [query, page]);

  function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPage(1);
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-4">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-xl font-semibold">Agent Marketplace</h1>
          <p className="mt-0.5 text-sm text-neutral-500">
            Discover and reuse AI agents built by the community
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl p-6 space-y-6">
        {/* Search */}
        <form onSubmit={handleSearch} className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
          <input
            type="search"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            placeholder="Search agents by name or description…"
            className="w-full rounded-md border bg-white py-2.5 pl-9 pr-4 text-sm outline-none focus:ring-2 focus:ring-neutral-900"
          />
        </form>

        {/* Results */}
        <div>
          <p className="mb-3 text-sm text-neutral-500">
            {loading ? "Loading…" : `${total} agent${total !== 1 ? "s" : ""}`}
          </p>

          {!loading && agents.length === 0 && (
            <p className="text-sm text-neutral-400">No agents found.</p>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <Link
                key={agent.agentId}
                href={`/marketplace/${agent.agentId}`}
                className="rounded-xl border bg-white p-5 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <h3 className="font-medium">{agent.name}</h3>
                  <span className="text-xs text-neutral-400">
                    {agent.callCount.toLocaleString()} calls
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-neutral-500">
                  {agent.description || "No description."}
                </p>
                <div className="mt-3 flex gap-2 text-xs text-neutral-400">
                  <span>{agent.inputSchema.length} inputs</span>
                  <span>·</span>
                  <span>{agent.outputSchema.length} outputs</span>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Pagination */}
        {total > 20 && (
          <div className="flex justify-center gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded border px-3 py-1 text-sm disabled:opacity-40"
            >
              Previous
            </button>
            <span className="px-2 py-1 text-sm text-neutral-500">
              Page {page}
            </span>
            <button
              disabled={agents.length < 20}
              onClick={() => setPage((p) => p + 1)}
              className="rounded border px-3 py-1 text-sm disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
