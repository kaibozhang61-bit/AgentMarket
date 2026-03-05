"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Loader2, Send } from "lucide-react";
import { AppLayout } from "@/components/layout/app-layout";
import { StepCanvas, AGENT_FRAME_ID, BLACKBOARD_ID } from "@/components/workflows/step-canvas";
import { ResizeHandle } from "@/components/agents/resize-handle";
import { StepDetailPanel } from "@/components/agents/step-detail-panel";
import { AgentDetailPanel } from "@/components/agents/agent-detail-panel";
import { RunHistoryPanel } from "@/components/agents/run-history-panel";
import { agentsApi } from "@/lib/api";
import { useAutoSave } from "@/lib/use-auto-save";
import type { WorkflowStep } from "@/lib/types";

interface Props {
  agentId?: string; // undefined = new agent, string = existing agent
}

interface ChatMessage {
  role: "assistant" | "user";
  content: string;
}

interface DraftPayload {
  name?: string;
  description?: string;
  steps?: DraftStep[];
  inputSchema?: Record<string, unknown>[];
  outputSchema?: Record<string, unknown>[];
}

interface DraftStep {
  order: number;
  type: string;
  systemPrompt?: string;
  agentId?: string;
  inputSchema?: Record<string, unknown>[];
  outputSchema?: Record<string, unknown>[];
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    role: "assistant",
    content:
      "Hi! Describe the agent you want to build and I'll help you design it.",
  },
];

/** Extract the display message from raw chat content.
 *  Assistant messages may be raw JSON from the LLM — extract the "message" field. */
function extractDisplayMessage(role: string, content: string): string {
  if (role === "user") return content;
  // Try to parse as JSON and extract the message field
  // The LLM response may be wrapped in markdown code fences
  let cleaned = content.trim();
  if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "").trim();
  }
  try {
    const parsed = JSON.parse(cleaned);
    if (typeof parsed === "object" && parsed !== null && typeof parsed.message === "string") {
      return parsed.message;
    }
  } catch {
    // Not JSON — return as-is
  }
  return content;
}

function toCanvasStep(draft: DraftStep, index: number): WorkflowStep {
  const stepId = (draft as Record<string, unknown>).stepId as string ?? `draft-${index + 1}`;
  const base = {
    stepId,
    order: draft.order ?? index + 1,
    inputSchema: draft.inputSchema,
    outputSchema: draft.outputSchema as Record<string, unknown> | undefined,
  };
  const t = (draft.type ?? "llm").toLowerCase();
  if (t === "llm") {
    return { ...base, type: "LLM", systemPrompt: draft.systemPrompt ?? "", prompt: draft.systemPrompt ?? "" };
  }
  if (t === "agent") {
    return { ...base, type: "AGENT", agentId: draft.agentId ?? "" };
  }
  return { ...base, type: t.toUpperCase(), systemPrompt: draft.systemPrompt ?? "", prompt: draft.systemPrompt ?? "" };
}

export function AgentEditor({ agentId: initialAgentId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [agentId, setAgentId] = useState<string | null>(initialAgentId ?? null);
  const [stage, setStage] = useState("clarifying");
  const [agentStatus, setAgentStatus] = useState<string>("draft");

  const [agentName, setAgentName] = useState("Untitled Agent");
  const [agentDescription, setAgentDescription] = useState("");
  const [agentInputSchema, setAgentInputSchema] = useState<Record<string, unknown>[]>([]);
  const [agentOutputSchema, setAgentOutputSchema] = useState<Record<string, unknown>[]>([]);
  const [steps, setSteps] = useState<WorkflowStep[]>([]);

  // Resizable column widths (px)
  const [leftWidth, setLeftWidth] = useState(288);   // 18rem default
  const [rightWidth, setRightWidth] = useState(256);  // 16rem default
  const MIN_WIDTH = 180;
  const MAX_WIDTH = 500;

  const onResizeLeft = useCallback((delta: number) => {
    setLeftWidth((w) => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w + delta)));
  }, []);

  const onResizeRight = useCallback((delta: number) => {
    setRightWidth((w) => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w + delta)));
  }, []);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftPayload | null>(null);

  const [highlightedAgentIds, setHighlightedAgentIds] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [showTestRunModal, setShowTestRunModal] = useState(false);
  const [testRunInput, setTestRunInput] = useState("{}");
  const [testRunning, setTestRunning] = useState(false);
  const [testRunResult, setTestRunResult] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load existing agent + session on mount
  useEffect(() => {
    if (!initialAgentId) return;
    // Load agent data for canvas
    agentsApi.get(initialAgentId).then((agent) => {
      setAgentName(agent.name);
      setAgentDescription(agent.description);
      setAgentStatus(agent.status);
      setAgentInputSchema(agent.inputSchema as unknown as Record<string, unknown>[]);
      setAgentOutputSchema(agent.outputSchema as unknown as Record<string, unknown>[]);
      const rawSteps = (agent.steps ?? []) as DraftStep[];
      setSteps(rawSteps.map(toCanvasStep));
      setDraft({ name: agent.name, description: agent.description, steps: rawSteps });
    }).catch(() => {});
    // Load chat session for resume
    agentsApi.getSession(initialAgentId).then((session) => {
      setSessionId(session.sessionId);
      setAgentId(session.agentId);
      setStage(session.stage);
      if (session.messages.length > 0) {
        setMessages([
          ...INITIAL_MESSAGES,
          ...session.messages.map((m) => ({
            role: m.role as "user" | "assistant",
            content: extractDisplayMessage(m.role, m.content),
          })),
        ]);
      }
    }).catch(() => {});
  }, [initialAgentId]);

  // Dirty flag — only auto-save when user actually made changes
  const isDirty = useRef(false);
  const loadedRef = useRef(false);

  // Auto-save
  const triggerAutoSave = useAutoSave(async () => {
    if (!agentId || !draft || !isDirty.current) return;
    await agentsApi.saveDraft(agentId, {
      name: agentName,
      description: draft.description,
      steps: draft.steps as Record<string, unknown>[],
    });
  }, 1500);

  useEffect(() => {
    // Skip the initial load — only trigger on actual user changes
    if (!loadedRef.current) {
      if (agentId && draft) loadedRef.current = true;
      return;
    }
    if (agentId && draft) {
      isDirty.current = true;
      triggerAutoSave();
    }
  }, [draft, agentName, agentId, triggerAutoSave]);

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    // Handle "reverify" keyword
    if (trimmed.toLowerCase() === "reverify" && publishConcerns.length > 0) {
      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
      handleVerifyPublish();
      return;
    }

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);
    try {
      const res = await agentsApi.chat({
        message: trimmed,
        sessionId: sessionId ?? undefined,
        agentId: agentId ?? undefined,
      });
      setSessionId(res.sessionId);
      setAgentId(res.agentId);
      setStage(res.stage);
      // Update URL if this is a new agent
      if (!initialAgentId && res.agentId) {
        window.history.replaceState(null, "", `/agents/${res.agentId}/edit`);
      }
      if (res.draft) {
        setDraft(res.draft);
        setSteps((res.draft.steps ?? []).map(toCanvasStep));
        if (res.draft.name) setAgentName(res.draft.name);
      }
      setMessages((prev) => [...prev, { role: "assistant", content: res.message }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  }

  const [publishConcerns, setPublishConcerns] = useState<string[]>([]);
  const [verifying, setVerifying] = useState(false);

  async function handleVerifyPublish() {
    if (!agentId) return;
    setVerifying(true);
    setPublishConcerns([]);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "Verifying your agent before publishing..." },
    ]);
    try {
      const result = await agentsApi.verifyPublish(agentId);
      if (result.published) {
        setAgentStatus("published");
        setPublishConcerns([]);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Your agent has been verified and published to the marketplace!" },
        ]);
      } else {
        setPublishConcerns(result.concerns);
        const concernList = result.concerns.map((c, i) => `${i + 1}. ${c}`).join("\n");
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `I found some concerns with your agent:\n\n${concernList}\n\nPlease fix these issues and type "reverify", or click **Override** to publish anyway.`,
          },
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Verification failed";
      setMessages((prev) => [...prev, { role: "assistant", content: msg }]);
    } finally {
      setVerifying(false);
    }
  }

  async function handleOverridePublish() {
    if (!agentId) return;
    setSaving(true);
    try {
      await agentsApi.publish(agentId);
      setAgentStatus("published");
      setPublishConcerns([]);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Agent published (override). Concerns were skipped." },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Publish failed";
      setMessages((prev) => [...prev, { role: "assistant", content: msg }]);
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const selectedStep = steps.find((s) => s.stepId === selectedStepId) ?? null;

  function handleStepUpdated(updated: WorkflowStep) {
    setSteps((prev) => prev.map((s) => (s.stepId === updated.stepId ? updated : s)));
    // Also update the draft so auto-save picks it up
    setDraft((prev) => {
      if (!prev) return prev;
      const updatedSteps = (prev.steps ?? []).map((s) =>
        (s as Record<string, unknown>).stepId === updated.stepId
          ? { ...s, systemPrompt: updated.systemPrompt ?? updated.prompt }
          : s,
      );
      return { ...prev, steps: updatedSteps as DraftStep[] };
    });
    isDirty.current = true;
  }

  return (
    <AppLayout>
      <div className="-mx-6 -my-6 flex h-[calc(100vh)] overflow-hidden">
        {/* ── Left: Chat ── */}
        <div className="flex flex-shrink-0 flex-col border-r bg-white" style={{ width: leftWidth }}>
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <Bot className="h-4 w-4 text-neutral-500" />
            <span className="text-sm font-medium text-neutral-700">
              {initialAgentId ? "Edit with AI" : "Create with AI"}
            </span>
            {stage !== "clarifying" && (
              <span className="ml-auto rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-500">
                {stage}
              </span>
            )}
          </div>

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
                  {msg.role === "user" ? (
                    msg.content
                  ) : (
                    <div className="prose prose-xs prose-neutral max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_h1]:text-sm [&_h2]:text-sm [&_h3]:text-xs [&_code]:rounded [&_code]:bg-neutral-200 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_pre]:rounded-md [&_pre]:bg-neutral-800 [&_pre]:p-2 [&_pre]:text-xs [&_pre_code]:bg-transparent [&_pre_code]:p-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-xl bg-neutral-100 px-3 py-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-400" />
                  <span className="text-xs text-neutral-400">Thinking…</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <textarea
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
                placeholder="Describe your agent…"
                className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-neutral-900 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || sending}
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-neutral-900 text-white hover:bg-neutral-700 disabled:opacity-40"
              >
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-neutral-400">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>

        <ResizeHandle onResize={onResizeLeft} side="left" />

        {/* ── Middle: Canvas ── */}
        <div className="flex flex-1 flex-col bg-neutral-50">
          <div className="flex items-center justify-between border-b bg-white px-5 py-3">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-neutral-400" />
              <input
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                className="rounded px-1.5 py-0.5 text-sm font-medium text-neutral-800 outline-none hover:bg-neutral-100 focus:bg-neutral-100"
              />
              {agentStatus === "published" && (
                <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                  Published
                </span>
              )}
              {agentStatus === "draft" && (
                <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-500">
                  Draft · auto-saved
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled
                title="Coming soon"
                className="rounded-md border px-3 py-1.5 text-xs font-medium text-neutral-300 cursor-not-allowed"
              >
                Version History
              </button>
              {agentId && steps.length > 0 && (
                <button
                  onClick={() => setShowTestRunModal(true)}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700 disabled:opacity-40"
                >
                  Test Run
                </button>
              )}
              {agentStatus === "draft" && publishConcerns.length === 0 && (
                <button
                  onClick={handleVerifyPublish}
                  disabled={steps.length === 0 || saving || verifying}
                  className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-40"
                >
                  {verifying ? "Verifying…" : "Publish"}
                </button>
              )}
              {agentStatus === "draft" && publishConcerns.length > 0 && (
                <button
                  onClick={handleOverridePublish}
                  disabled={saving}
                  className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-40"
                >
                  {saving ? "Publishing…" : "Override"}
                </button>
              )}
            </div>
          </div>

          <div className="relative flex-1 overflow-y-auto">
            <StepCanvas
              steps={steps}
              agentName={agentName}
              agentInputSchema={agentInputSchema as unknown as import("@/lib/types").FieldSchema[]}
              agentOutputSchema={agentOutputSchema as unknown as import("@/lib/types").FieldSchema[]}
              selectedId={selectedStepId}
              onSelect={setSelectedStepId}
              onStepsReordered={(reordered) => {
                setSteps(reordered);
                isDirty.current = true;
                setDraft((prev) => prev ? { ...prev, steps: reordered as unknown as DraftStep[] } : prev);
              }}
            />
            <RunHistoryPanel agentId={agentId} />
          </div>
        </div>

        <ResizeHandle onResize={onResizeRight} side="right" />

        {/* ── Right: Detail Panel ── */}
        <div className="flex flex-shrink-0 flex-col border-l bg-white" style={{ width: rightWidth }}>
          {selectedStepId === AGENT_FRAME_ID || selectedStepId === BLACKBOARD_ID ? (
            <AgentDetailPanel
              agent={{
                name: agentName,
                description: agentDescription,
                status: agentStatus,
                inputSchema: agentInputSchema as unknown as import("@/lib/types").FieldSchema[],
                outputSchema: agentOutputSchema as unknown as import("@/lib/types").FieldSchema[],
                context: {},
                callCount: 0,
                lastUsedAt: null,
              }}
              stepOutputGroups={steps.map((s, i) => ({
                stepId: s.stepId,
                label: `Step ${i + 1}`,
                fields: (Array.isArray(s.outputSchema) ? s.outputSchema : []).map((f: Record<string, unknown>) => ({
                  fieldName: (f.fieldName as string) ?? "",
                  type: (f.type as string) ?? "string",
                  required: (f.required as boolean) ?? true,
                  description: (f.description as string) ?? "",
                  visibility: ((f.visibility as string) ?? "private") as "public" | "private",
                })),
              }))}
              onAgentUpdated={(fields) => {
                if (fields.name) setAgentName(fields.name);
                if (fields.description !== undefined) setAgentDescription(fields.description);
                if (fields.inputSchema) setAgentInputSchema(fields.inputSchema as unknown as Record<string, unknown>[]);
                if (fields.outputSchema) setAgentOutputSchema(fields.outputSchema as unknown as Record<string, unknown>[]);
                isDirty.current = true;
                setDraft((prev) => prev ? {
                  ...prev,
                  name: fields.name ?? prev.name,
                  description: fields.description ?? prev.description,
                  inputSchema: (fields.inputSchema ?? prev.inputSchema) as Record<string, unknown>[],
                  outputSchema: (fields.outputSchema ?? prev.outputSchema) as Record<string, unknown>[],
                } : prev);
              }}
              onVisibilityChanged={(stepId, fieldName, visibility) => {
                setSteps((prev) => prev.map((s) => {
                  if (s.stepId !== stepId) return s;
                  const schema = Array.isArray(s.outputSchema) ? s.outputSchema : [];
                  const updated = schema.map((f: Record<string, unknown>) =>
                    (f.fieldName as string) === fieldName ? { ...f, visibility } : f
                  );
                  return { ...s, outputSchema: updated as unknown as Record<string, unknown> };
                }));
                isDirty.current = true;
              }}
            />
          ) : (
            <StepDetailPanel
              step={selectedStep}
              agentId={agentId ?? undefined}
              isLastStep={selectedStep ? selectedStep.order === Math.max(...steps.map((s) => s.order)) : false}
              onStepUpdated={handleStepUpdated}
            />
          )}
        </div>
      </div>

      {/* Test Run Modal */}
      {showTestRunModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="mb-1 font-semibold">Test Run</h3>
            <p className="mb-4 text-xs text-neutral-500">
              Provide input for the agent, then run all steps end-to-end.
            </p>

            {/* Show input schema fields as hints */}
            {agentInputSchema.length > 0 && (
              <div className="mb-3 rounded-md bg-neutral-50 p-2">
                <p className="mb-1 text-xs font-medium text-neutral-400">Expected input fields:</p>
                <div className="space-y-0.5">
                  {agentInputSchema.map((f, i) => (
                    <p key={i} className="text-xs text-neutral-500">
                      <code className="text-neutral-700">{(f as Record<string, unknown>).fieldName as string}</code>
                      {" "}({(f as Record<string, unknown>).type as string})
                      {(f as Record<string, unknown>).required ? " — required" : ""}
                    </p>
                  ))}
                </div>
              </div>
            )}

            <textarea
              rows={6}
              value={testRunInput}
              onChange={(e) => setTestRunInput(e.target.value)}
              spellCheck={false}
              placeholder='{"emailThread": "Hi, I wanted to discuss..."}'
              className="w-full resize-y rounded-md border bg-neutral-50 px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-neutral-900"
            />

            {testRunResult && (
              <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-neutral-900 p-3 text-xs text-green-400">
                {testRunResult}
              </pre>
            )}

            <div className="mt-4 flex gap-2">
              <button
                onClick={async () => {
                  if (!agentId) return;
                  setTestRunning(true);
                  setTestRunResult(null);
                  try {
                    JSON.parse(testRunInput); // validate JSON
                    const res = await agentsApi.test(agentId, { input: JSON.parse(testRunInput) });
                    setTestRunResult(JSON.stringify(res.output, null, 2));
                  } catch (e: unknown) {
                    setTestRunResult(e instanceof Error ? e.message : "Run failed");
                  } finally {
                    setTestRunning(false);
                  }
                }}
                disabled={testRunning}
                className="flex-1 rounded-md bg-neutral-900 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
              >
                {testRunning ? "Running…" : "Run"}
              </button>
              <button
                onClick={() => {
                  setShowTestRunModal(false);
                  setTestRunResult(null);
                }}
                className="flex-1 rounded-md border py-2 text-sm font-medium text-neutral-600 hover:bg-neutral-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
