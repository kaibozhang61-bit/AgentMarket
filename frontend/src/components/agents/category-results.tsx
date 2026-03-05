"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Zap } from "lucide-react";
import type { CategoryGroup, SearchResult, MetricValue } from "@/lib/types";
import { SearchResults } from "@/components/agents/search-results";

interface Props {
  categories: CategoryGroup[];
  metrics?: Record<string, Record<string, MetricValue>>;
  metricsLoading?: boolean;
  onSelectAgents: (agentIds: string[]) => void;
  onCompose: (agentIds: string[], goal: string) => void;
  onSelectSingleAgent: (agentId: string) => void;
  onRequestMetrics: (metrics: string[]) => void;
  onRunAgent: (agentId: string, input: Record<string, unknown>) => void;
  onSwitchToPathC: () => void;
}

export function CategoryResults({
  categories,
  metrics,
  metricsLoading,
  onSelectAgents,
  onCompose,
  onSelectSingleAgent,
  onRequestMetrics,
  onRunAgent,
  onSwitchToPathC,
}: Props) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());

  function toggleCategory(category: string) {
    setExpandedCategory((prev) => (prev === category ? null : category));
  }

  function toggleAgent(agentId: string) {
    setSelectedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      onSelectAgents(Array.from(next));
      return next;
    });
  }

  function handleCompose() {
    const ids = Array.from(selectedAgents);
    if (ids.length > 0) {
      onCompose(ids, "");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-neutral-700">
          No direct match found
        </h3>
        <p className="mt-1 text-xs text-neutral-500">
          These categories may be useful. Pick agents from one or more
          categories and we'll compose them into a new agent.
        </p>
      </div>

      {/* Category list */}
      <div className="space-y-2">
        {categories.map((cat) => (
          <div key={cat.category} className="rounded-lg border">
            {/* Category header */}
            <button
              onClick={() => toggleCategory(cat.category)}
              className="flex w-full items-center justify-between px-3 py-2.5 text-left hover:bg-neutral-50"
              aria-expanded={expandedCategory === cat.category}
            >
              <div className="flex items-center gap-2">
                {expandedCategory === cat.category ? (
                  <ChevronDown className="h-3.5 w-3.5 text-neutral-400" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-neutral-400" />
                )}
                <span className="text-sm font-medium text-neutral-800">
                  {cat.category}
                </span>
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-500">
                  {cat.agents.length}
                </span>
              </div>
              <span className="text-xs text-neutral-400">
                max score: {(cat.max_score * 100).toFixed(0)}%
              </span>
            </button>

            {/* Expanded: show agents in this category */}
            {expandedCategory === cat.category && (
              <div className="border-t px-3 py-2">
                <div className="space-y-1.5">
                  {cat.agents.map((agent) => (
                    <div
                      key={agent.agent_id}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-neutral-50"
                    >
                      <input
                        type="checkbox"
                        id={`agent-${agent.agent_id}`}
                        checked={selectedAgents.has(agent.agent_id)}
                        onChange={() => toggleAgent(agent.agent_id)}
                        className="h-3.5 w-3.5 rounded border-neutral-300"
                      />
                      <label
                        htmlFor={`agent-${agent.agent_id}`}
                        className="flex-1 cursor-pointer"
                      >
                        <span className="text-xs font-medium text-neutral-800">
                          {agent.name}
                        </span>
                        <span className="ml-2 text-xs text-neutral-500">
                          {agent.description.slice(0, 60)}
                          {agent.description.length > 60 ? "…" : ""}
                        </span>
                      </label>
                      <span className="text-xs text-neutral-400">
                        {(agent.score * 100).toFixed(0)}%
                      </span>
                      <button
                        onClick={() => onSelectSingleAgent(agent.agent_id)}
                        className="rounded border px-2 py-0.5 text-xs text-neutral-600 hover:bg-neutral-100"
                      >
                        Use directly
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Compose button */}
      {selectedAgents.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-neutral-900 bg-neutral-50 p-3">
          <Zap className="h-4 w-4 text-neutral-700" />
          <div className="flex-1">
            <p className="text-xs font-medium text-neutral-800">
              {selectedAgents.size} agent{selectedAgents.size !== 1 ? "s" : ""} selected
            </p>
            <p className="text-xs text-neutral-500">
              Compose into a new agent
            </p>
          </div>
          <button
            onClick={handleCompose}
            className="rounded-md bg-neutral-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-neutral-700"
          >
            Compose
          </button>
        </div>
      )}

      {/* Path switching */}
      <div className="text-xs">
        <button
          onClick={onSwitchToPathC}
          className="text-neutral-500 hover:text-neutral-700 underline"
        >
          Build from scratch instead
        </button>
      </div>
    </div>
  );
}
