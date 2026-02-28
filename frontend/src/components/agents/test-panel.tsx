"use client";

import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { agentsApi } from "@/lib/api";
import type { FieldSchema } from "@/lib/types";

interface Props {
  agentId: string;
  inputSchema: FieldSchema[];
}

export function TestPanel({ agentId, inputSchema }: Props) {
  // Build initial JSON from schema
  const defaultInput = Object.fromEntries(
    inputSchema.map((f) => [f.fieldName, f.default ?? ""]),
  );
  const [inputText, setInputText] = useState(
    JSON.stringify(defaultInput, null, 2),
  );
  const [output, setOutput] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setError("");
    setOutput(null);
    setRunning(true);
    try {
      const parsed = JSON.parse(inputText);
      const res = await agentsApi.test(agentId, { input: parsed });
      setOutput(JSON.stringify(res.output, null, 2));
      setLatency(res.latency_ms);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Test failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-neutral-700">Test Panel</h3>
        {latency !== null && (
          <span className="text-xs text-neutral-400">{latency} ms</span>
        )}
      </div>

      {/* Input */}
      <div className="space-y-1">
        <p className="text-xs text-neutral-400">Input JSON</p>
        <textarea
          rows={5}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          spellCheck={false}
          className="w-full resize-y rounded-md border bg-neutral-50 px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-neutral-900"
        />
      </div>

      <button
        type="button"
        onClick={run}
        disabled={running}
        className="flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
      >
        {running ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {running ? "Running…" : "Run Test"}
      </button>

      {/* Error */}
      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600">
          {error}
        </p>
      )}

      {/* Output */}
      {output !== null && (
        <div className="space-y-1">
          <p className="text-xs text-neutral-400">Output</p>
          <pre className="overflow-x-auto rounded-md bg-neutral-900 p-3 text-xs text-green-400">
            {output}
          </pre>
        </div>
      )}
    </div>
  );
}
