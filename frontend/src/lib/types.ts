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
  searchResults?: SearchResults | null;
  selectedAgentId?: string | null;
  executionMode?: string | null;
  executionInput?: Record<string, unknown> | null;
  compositionAgents?: string[] | null;
}

// ── Search Results ───────────────────────────────────────────────────────────

export interface SearchResult {
  agent_id: string;
  name: string;
  description: string;
  category: string;
  score: number;
}

export interface CategoryGroup {
  category: string;
  max_score: number;
  agents: SearchResult[];
}

export interface SearchResults {
  path: "direct" | "indirect" | "no_results";
  results: SearchResult[];
  categories: CategoryGroup[];
}

// ── Metrics ──────────────────────────────────────────────────────────────────

export interface MetricValue {
  status: "available" | "unavailable" | "no_data";
  value?: number;
  sample_size?: number;
  indicative_only?: boolean;
}

export interface MetricsAnalysis {
  sessionId: string;
  status: "analyzing" | "complete";
  metricResults: Record<string, Record<string, MetricValue>>;
  missingMetrics: string[];
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
  isComposed?: boolean;
}

// ── Step (used by canvas and agent detail pages) ─────────────────────────────

export interface Step {
  stepId: string;
  order: number;
  type: string;                    // llm | agent | logic
  agentId?: string;
  prompt?: string;
  systemPrompt?: string;
  outputSchema?: Record<string, unknown> | Record<string, unknown>[];
  inputMapping?: Record<string, string>;
  missingFieldsResolution?: Record<string, unknown>;
  inputSchema?: Record<string, unknown>[];
  readFromBlackboard?: string[];
  // Logic step fields (Step Functions compatible)
  logicType?: "condition" | "transform" | "user_input";
  condition?: {
    field: string;
    threshold: number;
    then: string;
    else: string;
  };
  transforms?: {
    output_field: string;
    method: "static" | "llm" | "regex" | "template";
    value?: unknown;
    from_field?: string;
    prompt?: string;
    pattern?: string;
    template?: string;
  }[];
  question?: string;               // for user_input steps
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
