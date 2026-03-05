"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FieldSchema, WorkflowStep } from "@/lib/types";

/* ── Exported IDs ────────────────────────────────────────────────────────── */

export const AGENT_FRAME_ID = "__agent__";
export const BLACKBOARD_ID = "__blackboard__";

/* ── Props ───────────────────────────────────────────────────────────────── */

interface Props {
  steps: WorkflowStep[];
  agentName?: string;
  agentInputSchema?: FieldSchema[];
  agentOutputSchema?: FieldSchema[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onStepsReordered?: (reordered: WorkflowStep[]) => void;
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function outputFields(schema: unknown): { name: string; vis: string }[] {
  if (!Array.isArray(schema)) return [];
  return schema.map((f) => ({
    name: (f as Record<string, unknown>).fieldName as string ?? "?",
    vis: ((f as Record<string, unknown>).visibility as string) ?? "private",
  }));
}

function stepTitle(step: WorkflowStep): string {
  const t = step.type.toUpperCase();
  if (t === "AGENT") return step.agentId ? `Agent: ${step.agentId.slice(0, 14)}` : "Marketplace Agent";
  const p = step.prompt ?? step.systemPrompt ?? "";
  return p.length > 40 ? p.slice(0, 40) + "..." : p || "LLM Step";
}

/* ── Custom node: Step card ──────────────────────────────────────────────── */

function StepNode({ data }: NodeProps) {
  const d = data as {
    label: string; idx: number; type: string; readCount: number;
    writeCount: number; selected: boolean; onSelect: () => void;
  };
  const isLlm = d.type.toLowerCase() === "llm";
  const dotColor = isLlm ? "bg-purple-600" : "bg-blue-600";
  const badgeBg = isLlm ? "bg-purple-50 text-purple-700" : "bg-blue-50 text-blue-700";

  return (
    <div
      onClick={(e) => { e.stopPropagation(); d.onSelect(); }}
      className={`w-48 rounded-xl border-2 bg-white p-3.5 shadow-sm transition-all cursor-pointer ${
        d.selected ? "border-neutral-800 shadow-xl ring-2 ring-neutral-200" : "border-neutral-200 hover:shadow-md"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-neutral-300 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} className="!bg-neutral-300 !w-2 !h-2" />
      <Handle id="bb" type="source" position={Position.Top} className="!bg-amber-400 !w-2 !h-2" />

      <div className="mb-2 flex items-center gap-2">
        <div className={`flex h-6 w-6 items-center justify-center rounded-full ${dotColor} text-xs font-bold text-white`}>
          {d.idx}
        </div>
        <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${badgeBg}`}>
          {d.type.toUpperCase()}
        </span>
      </div>
      <p className="text-xs text-neutral-600 line-clamp-2">{d.label}</p>
      {d.readCount > 0 && (
        <div className="mt-2 flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5">
          <span className="text-xs text-blue-400">&larr;</span>
          <span className="text-xs text-blue-600">reads {d.readCount} field{d.readCount !== 1 ? "s" : ""}</span>
        </div>
      )}
      {d.writeCount > 0 && (
        <div className="mt-1 flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5">
          <span className="text-xs text-amber-400">&rarr;</span>
          <span className="text-xs text-amber-600">writes {d.writeCount} field{d.writeCount !== 1 ? "s" : ""}</span>
        </div>
      )}
    </div>
  );
}

/* ── Custom node: Blackboard ─────────────────────────────────────────────── */

function BlackboardNode({ data }: NodeProps) {
  const d = data as {
    agentName: string;
    stepCount: number;
    inputFields: { name: string; type: string }[];
    agentOutputFields: { name: string; type: string }[];
    stepGroups: { idx: number; fields: { name: string; vis: string }[] }[];
    selected: boolean; onSelect: () => void;
  };

  return (
    <div
      onClick={(e) => { e.stopPropagation(); d.onSelect(); }}
      className={`min-w-[300px] cursor-pointer rounded-xl border-2 bg-white p-4 shadow-sm transition-all ${
        d.selected ? "border-amber-400 shadow-lg" : "border-neutral-200 hover:shadow-md"
      }`}
    >
      <Handle type="target" position={Position.Bottom} className="!bg-amber-400 !w-2 !h-2" />

      {/* Agent header */}
      <div className="mb-3 flex items-center gap-3 border-b pb-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-900 text-sm font-bold text-white">A</div>
        <div>
          <p className="text-sm font-semibold text-neutral-800">{d.agentName}</p>
          <p className="text-xs text-neutral-400">{d.stepCount} step{d.stepCount !== 1 ? "s" : ""}</p>
        </div>
      </div>

      {/* Blackboard section */}
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-5 w-5 items-center justify-center rounded-md bg-amber-500 text-xs font-bold text-white">B</div>
        <span className="text-xs font-semibold text-amber-800">Blackboard</span>
      </div>

      <div className="space-y-2">
        {/* Agent I/O group */}
        {(d.inputFields.length > 0 || d.agentOutputFields.length > 0) && (
          <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-2.5">
            <p className="mb-1.5 text-xs font-semibold text-neutral-500">Agent I/O</p>
            {d.inputFields.length > 0 && (
              <div className="mb-1.5">
                <p className="mb-0.5 text-xs text-neutral-400">Input</p>
                {d.inputFields.map((f) => (
                  <p key={f.name} className="text-xs text-neutral-600 pl-1">
                    <span>&#x1F4E5;</span> <code>{f.name}</code> <span className="text-neutral-300">{f.type}</span>
                  </p>
                ))}
              </div>
            )}
            {d.agentOutputFields.length > 0 && (
              <div>
                <p className="mb-0.5 text-xs text-neutral-400">Output</p>
                {d.agentOutputFields.map((f) => (
                  <p key={f.name} className="text-xs text-neutral-600 pl-1">
                    <span>&#x1F4E4;</span> <code>{f.name}</code> <span className="text-neutral-300">{f.type}</span>
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step outputs group */}
        {d.stepGroups.some((g) => g.fields.length > 0) && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/30 p-2.5">
            <p className="mb-1.5 text-xs font-semibold text-amber-600">Step Outputs</p>
            <div className="space-y-1.5">
              {d.stepGroups.map((g) => g.fields.length > 0 && (
                <div key={g.idx}>
                  <p className="text-xs text-amber-500">Step {g.idx}</p>
                  {g.fields.map((f) => (
                    <p key={f.name} className="text-xs text-neutral-600 pl-1">
                      {f.vis === "public" ? "\uD83C\uDF10" : "\uD83D\uDD12"} <code>{f.name}</code>
                    </p>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {d.inputFields.length === 0 && d.agentOutputFields.length === 0 && d.stepGroups.every((g) => g.fields.length === 0) && (
          <p className="py-1 text-xs text-neutral-400">No fields yet</p>
        )}
      </div>
    </div>
  );
}

/* ── Custom node: Agent frame (just a label) ─────────────────────────────── */

function AgentLabelNode({ data }: NodeProps) {
  const d = data as { name: string; stepCount: number; selected: boolean; onSelect: () => void };
  return (
    <div
      onClick={(e) => { e.stopPropagation(); d.onSelect(); }}
      className={`cursor-pointer rounded-xl border-2 px-5 py-3 transition-all ${
        d.selected ? "border-blue-400 bg-blue-50/30 shadow-md" : "border-neutral-200 bg-white/80 hover:border-neutral-300"
      }`}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-900 text-sm font-bold text-white">A</div>
        <div>
          <p className="text-sm font-semibold text-neutral-800">{d.name || "Untitled Agent"}</p>
          <p className="text-xs text-neutral-400">{d.stepCount} step{d.stepCount !== 1 ? "s" : ""}</p>
        </div>
      </div>
    </div>
  );
}

/* ── Node types registry ─────────────────────────────────────────────────── */

const nodeTypes: NodeTypes = {
  stepNode: StepNode,
  blackboardNode: BlackboardNode,
  agentLabel: AgentLabelNode,
};

/* ── Main component ──────────────────────────────────────────────────────── */

export function StepCanvas({ steps, agentName, agentInputSchema, agentOutputSchema, selectedId, onSelect }: Props) {
  const sorted = useMemo(() => [...steps].sort((a, b) => a.order - b.order), [steps]);

  // Build nodes
  const initialNodes = useMemo(() => {
    const nodes: Node[] = [];
    const STEP_W = 210;
    const STEP_GAP = 60;
    const stepsStartX = 50;
    const stepsY = 280;
    const totalStepsWidth = sorted.length * STEP_W + (sorted.length - 1) * STEP_GAP;

    // Blackboard node (includes agent name as header)
    const inputFields = (agentInputSchema ?? []).map((f) => ({ name: f.fieldName, type: f.type }));
    const agentOutputFields = (agentOutputSchema ?? []).map((f) => ({ name: f.fieldName, type: f.type }));
    const stepGroups = sorted.map((step, i) => ({ idx: i + 1, fields: outputFields(step.outputSchema) }));
    nodes.push({
      id: BLACKBOARD_ID,
      type: "blackboardNode",
      position: { x: stepsStartX + totalStepsWidth / 2 - 200, y: 20 },
      data: {
        agentName: agentName || "Untitled Agent",
        stepCount: sorted.length,
        inputFields,
        agentOutputFields,
        stepGroups,
        selected: selectedId === BLACKBOARD_ID || selectedId === AGENT_FRAME_ID,
        onSelect: () => onSelect(BLACKBOARD_ID),
      },
      draggable: true,
    });

    // Step nodes
    sorted.forEach((step, i) => {
      nodes.push({
        id: step.stepId,
        type: "stepNode",
        position: { x: stepsStartX + i * (STEP_W + STEP_GAP), y: stepsY },
        data: {
          label: stepTitle(step),
          idx: i + 1,
          type: step.type,
          readCount: (step.readFromBlackboard ?? []).length,
          writeCount: outputFields(step.outputSchema).length,
          selected: selectedId === step.stepId,
          onSelect: () => onSelect(step.stepId),
        },
        draggable: true,
      });
    });

    return nodes;
  }, [sorted, agentName, agentInputSchema, selectedId, onSelect]);

  // Build edges
  const initialEdges = useMemo(() => {
    const edges: Edge[] = [];

    // Step-to-step horizontal edges
    sorted.forEach((step, i) => {
      if (i < sorted.length - 1) {
        edges.push({
          id: `e-${step.stepId}-${sorted[i + 1].stepId}`,
          source: step.stepId,
          target: sorted[i + 1].stepId,
          animated: false,
          style: { stroke: "#d4d4d4", strokeWidth: 2 },
        });
      }
    });

    // Step-to-blackboard edges (for steps with output)
    sorted.forEach((step) => {
      if (outputFields(step.outputSchema).length > 0) {
        edges.push({
          id: `e-bb-${step.stepId}`,
          source: step.stepId,
          sourceHandle: "bb",
          target: BLACKBOARD_ID,
          animated: true,
          style: { stroke: "#f59e0b", strokeWidth: 2 },
        });
      }
    });

    return edges;
  }, [sorted]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Only reset layout when steps actually change (add/remove), not on selection
  const prevStepIds = useRef<string[]>([]);
  useEffect(() => {
    const newIds = sorted.map((s) => s.stepId);
    const stepsChanged = newIds.join(",") !== prevStepIds.current.join(",");
    if (stepsChanged || prevStepIds.current.length === 0) {
      prevStepIds.current = newIds;
      setNodes(initialNodes);
      setEdges(initialEdges);
    }
  }, [sorted, initialNodes, initialEdges, setNodes, setEdges]);

  // Update node data (selection state) without resetting positions
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === BLACKBOARD_ID) {
          return { ...n, data: { ...n.data, selected: selectedId === BLACKBOARD_ID || selectedId === AGENT_FRAME_ID } };
        }
        const step = sorted.find((s) => s.stepId === n.id);
        if (step) {
          return { ...n, data: { ...n.data, selected: selectedId === n.id } };
        }
        return n;
      }),
    );
  }, [selectedId, sorted, setNodes]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onSelect(node.id);
  }, [onSelect]);

  if (sorted.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-center text-sm text-neutral-400">
          No steps yet. Describe your agent in the chat to get started.
        </p>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e5e5e5" gap={20} />
        <Controls position="top-right" />
        <MiniMap
          nodeColor={(n) => {
            if (n.id === BLACKBOARD_ID) return "#f59e0b";
            return n.data?.type?.toLowerCase() === "llm" ? "#9333ea" : "#2563eb";
          }}
          position="bottom-right"
        />
      </ReactFlow>
    </div>
  );
}
