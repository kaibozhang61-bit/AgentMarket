"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Search, Send, Workflow } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { StepCanvas } from "@/components/workflows/step-canvas";
import { marketplaceApi, orchestratorApi } from "@/lib/api";
import type { DraftStep, LogicType, MarketplaceAgent, WorkflowStep } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Convert a DraftStep (from AI) to a WorkflowStep (for the canvas) */
function toWorkflowStep(draft: DraftStep, index: number): WorkflowStep {
  const stepId = `draft-${index + 1}`;
  const base = { stepId, order: draft.order };

  if (draft.type === "AGENT") {
    return {
      ...base,
      type: "AGENT",
      // Show agentName if available so the canvas label is readable
      agentId: draft.agentName ?? draft.agentId ?? "(unknown agent)",
    };
  }
  if (draft.type === "LLM") {
    return { ...base, type: "LLM", prompt: draft.prompt ?? "" };
  }
  return {
    ...base,
    type: "LOGIC",
    logicType: (draft.logicType ?? "condition") as LogicType,
  };
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: "assistant" | "user";
  content: string;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    role: "assistant",
    content:
      "Hi! Describe the workflow you want to build and I'll generate a draft for you.",
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewWorkflowPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const [workflowName, setWorkflowName] = useState("Untitled Workflow");
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  const [agents, setAgents] = useState<MarketplaceAgent[]>([]);
  const [agentSearch, setAgentSearch] = useState("");
  const [highlightedAgentIds, setHighlightedAgentIds] = useState<Set<string>>(new Set());

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load real marketplace agents on mount
  useEffect(() => {
    marketplaceApi.list({ limit: 50 }).then((res) => setAgents(res.agents)).catch(() => {});
  }, []);

  // Auto-scroll chat to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const filteredAgents = agents.filter(
    (a) =>
      agentSearch === "" ||
      a.name.toLowerCase().includes(agentSearch.toLowerCase()) ||
      a.description.toLowerCase().includes(agentSearch.toLowerCase()),
  );

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);

    try {
      const res = await orchestratorApi.chat(trimmed);

      const workflowSteps = (res.draftSteps ?? []).map(toWorkflowStep);
      setSteps(workflowSteps);

      if (res.workflowName) setWorkflowName(res.workflowName);
      setHighlightedAgentIds(new Set(res.usedAgentIds ?? []));

      const summary = res.summary ?? `I've generated a ${workflowSteps.length}-step workflow draft.`;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `${summary} Review the canvas and confirm when ready.` },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <AppLayout>
      {/* Negate AppLayout's p-6 to go full-bleed */}
      <div className="-mx-6 -my-6 flex h-[calc(100vh-4rem)] overflow-hidden">

        {/* ── Left: Chat panel ─────────────────────────────────────── */}
        <div className="flex w-72 flex-shrink-0 flex-col border-r bg-white">
          {/* Header */}
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <Bot className="h-4 w-4 text-neutral-500" />
            <span className="text-sm font-medium text-neutral-700">Create with AI</span>
          </div>

          {/* Message history */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-neutral-900 text-white"
                      : "bg-neutral-100 text-neutral-700"
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-xl bg-neutral-100 px-3 py-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-400" />
                  <span className="text-xs text-neutral-400">Generating…</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <textarea
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
                placeholder="Describe your workflow…"
                className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-neutral-900 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || sending}
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-neutral-900 text-white hover:bg-neutral-700 disabled:opacity-40"
              >
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-neutral-400">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>

        {/* ── Middle: Canvas ───────────────────────────────────────── */}
        <div className="flex flex-1 flex-col bg-neutral-50">
          {/* Top bar */}
          <div className="flex items-center justify-between border-b bg-white px-5 py-3">
            <div className="flex items-center gap-2">
              <Workflow className="h-4 w-4 text-neutral-400" />
              <input
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                className="rounded px-1.5 py-0.5 text-sm font-medium text-neutral-800 outline-none hover:bg-neutral-100 focus:bg-neutral-100"
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled
                className="rounded-md border px-3 py-1.5 text-xs font-medium text-neutral-500 disabled:opacity-40"
              >
                Save as Draft
              </button>
              <button
                disabled={steps.length === 0}
                className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-40"
              >
                Confirm &amp; Save
              </button>
            </div>
          </div>

          {/* Canvas body */}
          <div className="flex-1 overflow-y-auto">
            <StepCanvas
              steps={steps}
              selectedId={selectedStepId}
              onSelect={setSelectedStepId}
            />
          </div>
        </div>

        {/* ── Right: Marketplace panel ─────────────────────────────── */}
        <div className="flex w-64 flex-shrink-0 flex-col border-l bg-white">
          {/* Header */}
          <div className="border-b px-4 py-3">
            <p className="text-sm font-medium text-neutral-700">Marketplace Agents</p>
          </div>

          {/* Search */}
          <div className="border-b px-3 py-2">
            <div className="flex items-center gap-2 rounded-md border bg-neutral-50 px-2.5 py-1.5">
              <Search className="h-3.5 w-3.5 flex-shrink-0 text-neutral-400" />
              <input
                value={agentSearch}
                onChange={(e) => setAgentSearch(e.target.value)}
                placeholder="Search agents…"
                className="flex-1 bg-transparent text-xs outline-none placeholder:text-neutral-400"
              />
            </div>
          </div>

          {/* Agent list */}
          <div className="flex-1 space-y-2 overflow-y-auto p-3">
            {filteredAgents.length === 0 ? (
              <p className="py-6 text-center text-xs text-neutral-400">
                {agents.length === 0 ? "Loading…" : "No agents found"}
              </p>
            ) : (
              filteredAgents.map((agent) => (
                <div
                  key={agent.agentId}
                  className={`rounded-lg border p-3 transition-all ${
                    highlightedAgentIds.has(agent.agentId)
                      ? "border-blue-400 bg-blue-50 shadow-sm"
                      : "border-neutral-200 bg-white hover:border-neutral-300"
                  }`}
                >
                  {highlightedAgentIds.has(agent.agentId) && (
                    <span className="mb-1.5 inline-block rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-700">
                      Used in draft
                    </span>
                  )}
                  <p className="text-xs font-medium text-neutral-800">{agent.name}</p>
                  <p className="mt-0.5 text-xs leading-snug text-neutral-400">
                    {agent.description}
                  </p>
                  <p className="mt-1.5 text-xs text-neutral-400">
                    {agent.callCount.toLocaleString()} calls
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </AppLayout>
  );
}
