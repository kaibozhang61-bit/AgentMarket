/**
 * API client — typed wrappers around fetch() for every backend endpoint.
 *
 * Base URL defaults to http://localhost:8000 (FastAPI dev server).
 * Set NEXT_PUBLIC_API_URL to override.
 */

import { getToken } from "@/lib/auth";
import type {
  Agent,
  AgentChatRequest,
  AgentChatResponse,
  AgentUpdateRequest,
  MarketplaceAgent,
} from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Fetch helper ─────────────────────────────────────────────────────────────

async function api<T>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(opts.headers as Record<string, string> ?? {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    let message = `Request failed: ${res.status}`;
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      // Pydantic validation errors — extract messages
      message = body.detail
        .map((e: Record<string, unknown>) => {
          const loc = Array.isArray(e.loc) ? e.loc.join(".") : "";
          return loc ? `${loc}: ${e.msg}` : String(e.msg ?? e);
        })
        .join("; ");
    } else if (body.detail) {
      message = JSON.stringify(body.detail);
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Users ────────────────────────────────────────────────────────────────────

export const usersApi = {
  getMe: () =>
    api<{ userId: string; email: string; username: string; createdAt: string; updatedAt: string }>(
      "/users/me",
    ),
  updateMe: (data: { username?: string }) =>
    api("/users/me", { method: "PUT", body: JSON.stringify(data) }),
};

// ── Agents ───────────────────────────────────────────────────────────────────

export const agentsApi = {
  listMine: () => api<{ agents: Agent[]; total: number }>("/agents/me"),

  create: (data: Record<string, unknown>) =>
    api<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),

  get: (agentId: string) => api<Agent>(`/agents/${agentId}`),

  update: (agentId: string, data: AgentUpdateRequest) =>
    api<Agent>(`/agents/${agentId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (agentId: string) =>
    api<void>(`/agents/${agentId}`, { method: "DELETE" }),

  publish: (agentId: string) =>
    api<Agent>(`/agents/${agentId}/publish`, { method: "POST" }),

  test: (agentId: string, data: { input: Record<string, unknown> }) =>
    api<{ output: Record<string, unknown>; latency_ms: number }>(
      `/agents/${agentId}/test`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  /** POST /agents/chat — 4-stage LLM-driven agent creation */
  chat: (data: AgentChatRequest) =>
    api<AgentChatResponse>("/agents/chat", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** GET /agents/{agentId}/session — load latest chat session for resume */
  getSession: (agentId: string) =>
    api<{
      sessionId: string;
      agentId: string;
      stage: string;
      messages: { role: string; content: string }[];
    }>(`/agents/${agentId}/session`),

  /** PUT /agents/{agentId}/draft — auto-save draft */
  saveDraft: (agentId: string, data: AgentUpdateRequest) =>
    api<Agent>(`/agents/${agentId}/draft`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** POST /agents/{agentId}/test-step — test a single step */
  testStep: (agentId: string, data: { stepId: string; input: Record<string, unknown> }) =>
    api<{ stepId: string; output: Record<string, unknown>; latency_ms: number }>(
      `/agents/${agentId}/test-step`,
      { method: "POST", body: JSON.stringify(data) },
    ),
};

// ── Marketplace ──────────────────────────────────────────────────────────────

export const marketplaceApi = {
  list: (params?: { page?: number; limit?: number; sort?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.sort) q.set("sort", params.sort);
    const qs = q.toString();
    return api<{ agents: MarketplaceAgent[]; total: number; page: number }>(
      `/marketplace/agents${qs ? `?${qs}` : ""}`,
    );
  },

  get: (agentId: string) =>
    api<MarketplaceAgent>(`/marketplace/agents/${agentId}`),

  search: (keyword: string, params?: { page?: number; limit?: number }) => {
    const q = new URLSearchParams({ q: keyword });
    if (params?.page) q.set("page", String(params.page));
    if (params?.limit) q.set("limit", String(params.limit));
    return api<{ agents: MarketplaceAgent[]; total: number; page: number }>(
      `/marketplace/agents/search?${q.toString()}`,
    );
  },
};
