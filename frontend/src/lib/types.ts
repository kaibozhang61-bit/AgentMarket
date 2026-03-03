// ── User ──────────────────────────────────────────────────────────────────────

export interface User {
  userId: string;
  email: string;
  username: string;
  createdAt: string;
  updatedAt: string;
}

// ── Field Schema ─────────────────────────────────────────────────────────────

export interface FieldSchema {
  fieldName: string;
  type: string;
  required: boolean;
  default?: unknown;
  description?: string;
  visibility?: "public" | "private";
}

// ── Agent ─────────────────────────────────────────────────────────────────────

export interface Agent {
  agentId: string;
  name: string;
  description: string;
  authorId: string;
  status: "draft" | "published" | "deprecated";
  visibility: "public" | "private";
  version: string;
  steps: Record<string, unknown>[];
  inputSchema: FieldSchema[];
  outputSchema: FieldSchema[];
  toolsRequired: string[];
  context: Record<string, string>;
  callCount: number;
  lastUsedAt: string | null;
  createdAt: string;
  updatedAt: string;
  systemPrompt?: string; // legacy compat — now inside steps
  level: string;
  tools: Record<string, unknown>[];
}

export interface AgentUpdateRequest {
  name?: string;
  description?: string;
  steps?: Record<string, unknown>[];
  visibility?: "public" | "private";
  inputSchema?: FieldSchema[];
  outputSchema?: FieldSchema[];
}

// ── Agent Chat ───────────────────────────────────────────────────────────────

export interface AgentChatRequest {
  message: string;
  sessionId?: string;
  agentId?: string;
}

export interface AgentChatDraft {
  name?: string;
  description?: string;
  steps?: Record<string, unknown>[];
  inputSchema?: Record<string, unknown>[];
  outputSchema?: Record<string, unknown>[];
}

export interface AgentChatResponse {
  sessionId: string;
  agentId: string;
  stage: string;
  message: string;
  draft: AgentChatDraft | null;
}

// ── Marketplace ──────────────────────────────────────────────────────────────

export interface MarketplaceAgent {
  agentId: string;
  name: string;
  description: string;
  authorId: string;
  version: string;
  status: string;
  visibility: string;
  inputSchema: FieldSchema[];
  outputSchema: FieldSchema[];
  callCount: number;
  createdAt: string;
  updatedAt: string;
  level: string;
}

// ── Step (used by canvas and agent detail pages) ─────────────────────────────

export interface Step {
  stepId: string;
  order: number;
  type: string;
  agentId?: string;
  prompt?: string;
  systemPrompt?: string;
  outputSchema?: Record<string, unknown> | Record<string, unknown>[];
  inputMapping?: Record<string, string>;
  missingFieldsResolution?: Record<string, unknown>;
  inputSchema?: Record<string, unknown>[];
  readFromBlackboard?: string[];  // e.g. ["agent_input.topic", "step_1_output.keywords"]
}

/** @deprecated Use Step instead */
export type WorkflowStep = Step;

export interface DraftStep {
  order: number;
  type: string;
  agentId?: string;
  agentName?: string;
  prompt?: string;
  systemPrompt?: string;
  description?: string;
}
