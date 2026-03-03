"use client";

import { useCallback, useRef, useState } from "react";
import type { FieldSchema, WorkflowStep } from "@/lib/types";

interface Props {
  steps: WorkflowStep[];
  agentName?: string;
  agentInputSchema?: FieldSchema[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onStepsReordered?: (reordered: WorkflowStep[]) => void;
}

const AGENT_FRAME_ID = "__agent__";
const BLACKBOARD_ID = "__blackboard__";

export { AGENT_FRAME_ID, BLACKBOARD_ID };

/* ── Helpers ─────────────────────────────────────────────────────────────── */

const TYPE_STYLE: Record<string, { border: string; bg: string; text: string; dot: string }> = {
  llm:   { border: "border-purple-200", bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-600" },
  LLM:   { border: "border-purple-200", bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-600" },
  agent: { border: "border-blue-200",   bg: "bg-blue-50",   text: "text-blue-700",   dot: "bg-blue-600" },
  AGENT: { border: "border-blue-200",   bg: "bg-blue-50",   text: "text-blue-700",   dot: "bg-blue-600" },
};
const DEFAULT_STYLE = { border: "border-neutral-200", bg: "bg-neutral-50", text: "text-neutral-700", dot: "bg-neutral-600" };

function getStyle(type: string) { return TYPE_STYLE[type] ?? DEFAULT_STYLE; }

function stepTitle(step: WorkflowStep): string {
  const t = step.type.toUpperCase();
  if (t === "AGENT") return step.agentId ? `Agent: ${step.agentId.slice(0, 12)}...` : "Marketplace Agent";
  if (t === "LLM") {
    const p = step.prompt ?? step.systemPrompt ?? "";
    return p.length > 35 ? p.slice(0, 35) + "..." : p || "LLM Step";
  }
  return step.type;
}

function outputFields(schema: unknown): { name: string; vis: string }[] {
  if (!Array.isArray(schema)) return [];
  return schema.map((f) => ({
    name: (f as Record<string, unknown>).fieldName as string ?? "?",
    vis: ((f as Record<string, unknown>).visibility as string) ?? "private",
  }));
}

/* ── Canvas Component ────────────────────────────────────────────────────── */

export function StepCanvas({ steps, agentName, agentInputSchema, selectedId, onSelect, onStepsReordered }: Props) {
  const sorted = [...steps].sort((a, b) => a.order - b.order);

  // Pan & zoom
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  // Card drag-to-reorder
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dropTargetIdx, setDropTargetIdx] = useState<number | null>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 1 || e.target === containerRef.current) {
      e.preventDefault();
      isDragging.current = true;
      dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    }
  }, [pan]);
  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current) return;
    setPan({ x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y });
  }, []);
  const onMouseUp = useCallback(() => { isDragging.current = false; }, []);
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.min(2, Math.max(0.3, z + (e.deltaY > 0 ? -0.05 : 0.05))));
  }, []);

  if (sorted.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-center text-sm text-neutral-400">
          No steps yet. Describe your agent in the chat to get started.
        </p>
      </div>
    );
  }

  // Blackboard data
  const inputFields = (agentInputSchema ?? []).map((f) => ({ name: f.fieldName, type: f.type }));
  const stepGroups = sorted.map((step, i) => ({
    idx: i + 1, stepId: step.stepId, fields: outputFields(step.outputSchema),
  }));

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden bg-neutral-50"
      style={{ cursor: isDragging.current ? "grabbing" : "grab" }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onWheel={onWheel}
    >
      {/* Zoom controls */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-0.5 rounded-lg border bg-white/90 px-1.5 py-1 shadow-sm backdrop-blur">
        <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.1))} className="rounded px-1.5 py-0.5 text-sm text-neutral-500 hover:bg-neutral-100">−</button>
        <span className="w-10 text-center text-xs text-neutral-400">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((z) => Math.min(2, z + 0.1))} className="rounded px-1.5 py-0.5 text-sm text-neutral-500 hover:bg-neutral-100">+</button>
        <div className="mx-1 h-4 w-px bg-neutral-200" />
        <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="rounded px-1.5 py-0.5 text-xs text-neutral-400 hover:bg-neutral-100">Fit</button>
      </div>

      {/* Pannable + zoomable content */}
      <div
        style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "center center" }}
        className="flex h-full items-center justify-center p-12"
      >
        {/* ── Agent frame ── */}
        <div
          onClick={(e) => {
            if (e.target === e.currentTarget || (e.target as HTMLElement).dataset?.agentFrame) onSelect(AGENT_FRAME_ID);
          }}
          className={`rounded-2xl border-2 p-6 transition-shadow ${
            selectedId === AGENT_FRAME_ID
              ? "border-blue-400 bg-blue-50/20 shadow-xl"
              : "border-neutral-200 bg-white/60 hover:border-neutral-300 hover:shadow-md"
          }`}
        >
          {/* Agent header */}
          <div data-agent-frame="true" className="mb-5 flex items-center gap-3" onClick={() => onSelect(AGENT_FRAME_ID)}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-900 text-sm font-bold text-white">A</div>
            <div>
              <p className="text-sm font-semibold text-neutral-800">{agentName || "Untitled Agent"}</p>
              <p className="text-xs text-neutral-400">{sorted.length} step{sorted.length !== 1 ? "s" : ""}</p>
            </div>
          </div>

          {/* ── Blackboard card ── */}
          <div
            onClick={(e) => { e.stopPropagation(); onSelect(BLACKBOARD_ID); }}
            className={`mb-5 cursor-pointer rounded-xl border-2 p-4 transition-all ${
              selectedId === BLACKBOARD_ID
                ? "border-amber-400 bg-amber-50 shadow-lg"
                : "border-amber-100 bg-amber-50/40 hover:border-amber-300 hover:shadow"
            }`}
          >
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500 text-xs font-bold text-white">B</div>
              <span className="text-xs font-semibold text-amber-800">Blackboard</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {/* Agent input group */}
              {inputFields.length > 0 && (
                <div className="rounded-lg border border-neutral-200 bg-white p-2.5 shadow-sm">
                  <p className="mb-1.5 text-xs font-semibold text-neutral-500">agent_input</p>
                  {inputFields.map((f) => (
                    <div key={f.name} className="flex items-center gap-1.5 py-0.5">
                      <span className="text-xs">📥</span>
                      <code className="text-xs font-medium text-neutral-700">{f.name}</code>
                      <span className="text-xs text-neutral-300">{f.type}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Step output groups */}
              {stepGroups.map((g) => g.fields.length > 0 && (
                <div key={g.stepId} className="rounded-lg border border-amber-200 bg-white p-2.5 shadow-sm">
                  <p className="mb-1.5 text-xs font-semibold text-amber-600">Step {g.idx} output</p>
                  {g.fields.map((f) => (
                    <div key={f.name} className="flex items-center gap-1.5 py-0.5">
                      <span className="text-xs">{f.vis === "public" ? "🌐" : "🔒"}</span>
                      <code className="text-xs font-medium text-neutral-700">{f.name}</code>
                    </div>
                  ))}
                </div>
              ))}

              {inputFields.length === 0 && stepGroups.every((g) => g.fields.length === 0) && (
                <p className="py-2 text-xs text-neutral-400">No fields yet — define outputSchema on your steps</p>
              )}
            </div>
          </div>

          {/* ── Arrows from steps to blackboard ── */}
          <div className="mb-1 flex justify-center">
            <div className="flex gap-5">
              {sorted.map((step) => {
                const has = outputFields(step.outputSchema).length > 0;
                return (
                  <div key={`a-${step.stepId}`} className="flex w-48 flex-col items-center">
                    {has ? (
                      <svg width="16" height="20" viewBox="0 0 16 20">
                        <line x1="8" y1="20" x2="8" y2="5" stroke="#f59e0b" strokeWidth="2" />
                        <polygon points="3,7 8,0 13,7" fill="#f59e0b" />
                      </svg>
                    ) : (
                      <div className="h-5" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Horizontal steps ── */}
          <div className="flex items-stretch justify-center gap-2">
            {sorted.map((step, i) => {
              const isLast = i === sorted.length - 1;
              const s = getStyle(step.type);
              const readFrom = step.readFromBlackboard ?? [];

              return (
                <div key={step.stepId} className="flex items-center">
                  {/* Step card — draggable */}
                  <div
                    draggable
                    onDragStart={() => setDraggedIdx(i)}
                    onDragOver={(e) => { e.preventDefault(); setDropTargetIdx(i); }}
                    onDragLeave={() => setDropTargetIdx(null)}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (draggedIdx !== null && draggedIdx !== i && onStepsReordered) {
                        const reordered = [...sorted];
                        const [moved] = reordered.splice(draggedIdx, 1);
                        reordered.splice(i, 0, moved);
                        onStepsReordered(reordered.map((s, idx) => ({ ...s, order: idx + 1 })));
                      }
                      setDraggedIdx(null);
                      setDropTargetIdx(null);
                    }}
                    onDragEnd={() => { setDraggedIdx(null); setDropTargetIdx(null); }}
                    onClick={(e) => { e.stopPropagation(); onSelect(step.stepId); }}
                    className={`w-48 cursor-pointer rounded-xl border-2 p-3.5 transition-all ${
                      draggedIdx === i ? "opacity-50" : ""
                    } ${
                      dropTargetIdx === i && draggedIdx !== i ? "ring-2 ring-blue-400" : ""
                    } ${
                      selectedId === step.stepId
                        ? "border-neutral-800 bg-white shadow-xl ring-2 ring-neutral-200"
                        : `${s.border} bg-white hover:shadow-md`
                    }`}
                  >
                    {/* Header */}
                    <div className="mb-2 flex items-center gap-2">
                      <div className={`flex h-6 w-6 items-center justify-center rounded-full ${s.dot} text-xs font-bold text-white`}>
                        {i + 1}
                      </div>
                      <span className={`rounded-md ${s.bg} px-2 py-0.5 text-xs font-semibold ${s.text}`}>
                        {step.type.toUpperCase()}
                      </span>
                    </div>

                    {/* Title */}
                    <p className="mb-1.5 text-xs leading-snug text-neutral-600 line-clamp-2">
                      {stepTitle(step)}
                    </p>

                    {/* Reads indicator */}
                    {readFrom.length > 0 && (
                      <div className="mt-2 flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1">
                        <span className="text-xs text-blue-400">←</span>
                        <span className="text-xs text-blue-600">
                          reads {readFrom.length} field{readFrom.length !== 1 ? "s" : ""}
                        </span>
                      </div>
                    )}

                    {/* Output count */}
                    {outputFields(step.outputSchema).length > 0 && (
                      <div className="mt-1.5 flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1">
                        <span className="text-xs text-amber-400">→</span>
                        <span className="text-xs text-amber-600">
                          writes {outputFields(step.outputSchema).length} field{outputFields(step.outputSchema).length !== 1 ? "s" : ""}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Arrow to next step */}
                  {!isLast && (
                    <svg width="28" height="20" viewBox="0 0 28 20" className="mx-0.5 shrink-0">
                      <line x1="2" y1="10" x2="20" y2="10" stroke="#d4d4d4" strokeWidth="2" />
                      <polygon points="18,4 26,10 18,16" fill="#d4d4d4" />
                    </svg>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
