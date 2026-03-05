"""
AgentChatService — POST /agents/chat

Search-first, 3-path routing agent chat flow:

  CLARIFYING  → ask follow-up questions (max 2 rounds, 1 question per round)
  SEARCHING   → call search_agents, classify results into 3 paths
  PATH_A      → direct match: comparison table + execution modes
  PATH_B      → indirect match: category list + composition
  PATH_C      → no match: agent creation flow (planning → editing)
  PLANNING    → generate agent draft (Path C or after composition)
  EDITING     → apply user modifications to the existing draft
  SAVED       → agent saved

Session history is persisted in DDB (AgentChatSession entity) so the
frontend only needs to send { message, sessionId, agentId }.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic

from app.core.config import get_settings
from app.dao.agent_chat_session_dao import AgentChatSessionDAO
from app.dao.agent_dao import AgentDAO

_settings = get_settings()
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)


# ── System prompt for search-first flow ───────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an AI Agent marketplace assistant. You help users find, compare, \
execute, and create AI Agents. You MUST follow the protocol below and \
ALWAYS respond with strict JSON — no markdown, no explanation outside the JSON.

## Core Rule
Always search first. Never ask "are you searching or creating?"
When a user expresses any need, clarify intent then search automatically.

## Stages

### CLARIFYING
- Ask follow-up questions to clarify the user's intent (max 2 rounds, \
1 question per round with multiple choice options).
- After clarification, generate search parameters and move to SEARCHING.
- Never assume what the user wants.

### SEARCHING
- You have generated search parameters: task_description, available_inputs, \
desired_outputs.
- Include these in the "search_params" field of your response.
- The backend will call search_agents and return results.
- You will then be called again with the search results to route.

### PATH_A (Direct Match — score ≥ 0.85)
- Show agent comparison table (up to 5 results + 1 free new agent option).
- Ask which metrics the user cares about (suggest: success rate, etc.).
- When user selects an agent, confirm before execution.
- Support path switching: user can say "none of these fit" → PATH_B, \
"build from scratch" → PATH_C.

### PATH_B (Indirect Match — 0.50 ≤ score < 0.85)
- Show categories grouped by similarity.
- User selects agents from categories → trigger composition.
- Support path switching: user can select one agent directly → PATH_A, \
"build from scratch" → PATH_C.

### PATH_C (No Match — score < 0.50)
- Enter agent creation flow directly.
- Carry over task/input/output from clarification phase.
- Same as PLANNING stage below.

### PLANNING
- Generate agent draft (simple or composite).
- Simple Agent: single step with type="llm".
- Composite Agent: multiple steps chained together.

#### Step Types (Step Functions compatible)
Each step maps directly to a Step Functions state. Use the correct type:

1. type="llm" — calls Claude via Lambda (Task State)
   Required fields: stepId, order, type, systemPrompt, inputSchema, \
outputSchema, readFromBlackboard.

2. type="agent" — delegates to another published Agent (WaitForTaskToken)
   Required fields: stepId, order, type, agentId, outputSchema, \
readFromBlackboard.

3. type="logic", logicType="condition" — branching (Choice State, zero latency)
   Required fields: stepId, order, type, logicType, condition.
   condition must have: field (dot-path to previous output), threshold \
(numeric), then (stepId to jump to), else (stepId to jump to).
   No Lambda invoked — native Step Functions branching.
   Example:
   {{
     "stepId": "check-score", "order": 3, "type": "logic",
     "logicType": "condition",
     "condition": {{
       "field": "success_score",
       "threshold": 0.7,
       "then": "send-email",
       "else": "fallback-step"
     }}
   }}

4. type="logic", logicType="transform" — field transformation (Task State)
   Required fields: stepId, order, type, logicType, transforms, outputSchema.
   transforms is an array, each with: output_field, method \
(static|llm|regex|template), and method-specific fields.
   Use when upstream output field names don't match downstream input names.

5. type="logic", logicType="user_input" — pause for user input \
(WaitForTaskToken, 1hr timeout)
   Required fields: stepId, order, type, logicType, question, outputSchema.
   Execution pauses, user sees the question, submits answer, execution resumes.

#### Blackboard — context sharing between steps:
Steps share data through a blackboard (shared key-value store).
At runtime, agent input is written as "agent_input" and each step's output \
is written as "step_{{stepId}}_output".

For EVERY step (except type="logic"/logicType="condition") you MUST generate:
1. outputSchema — MANDATORY. Each field: fieldName, type, required, \
description, visibility ("public" or "private").
2. readFromBlackboard — dot-path references to blackboard fields.
   Format: "agent_input.fieldName" or "step_{{prevStepId}}_output.fieldName"

#### Step Functions constraints:
- Steps execute in order (or branch via condition steps).
- Each step runs in its own Lambda — no shared in-memory state.
- All inter-step data flows through the blackboard (DynamoDB).
- Condition steps read from the previous step's output directly \
($.output.fieldName) — no Lambda needed.
- Agent steps use WaitForTaskToken — the outer state machine suspends \
until the inner agent completes.
- Keep step count reasonable (≤ 10 steps recommended).

### EDITING
- Apply user modifications to the draft.
- Stay until user saves.

### SAVED
- Confirm the agent has been saved.

## Execution Modes (when user selects an agent in PATH_A)
1. Chat-driven: user provides input conversationally, you extract fields.
2. Form-based: return "execution_mode": "form" to show auto-generated form.
3. Hybrid: user describes input in chat, you pre-fill form fields.

Before calling run, ALWAYS show confirmation with inputs and ask user to confirm.

## Path Switching
Users are never locked into a path:
- PATH_A → PATH_B: "None of these fit exactly"
- PATH_A → PATH_C: "I want to build from scratch"
- PATH_B → PATH_A: User clicks a single agent → "Use this one directly"
- PATH_B → PATH_C: "Let me build from scratch"
- PATH_C → SEARCHING: "Search again" or "find something similar"
- Any path → SEARCHING: User describes a new need at any time

## Response format (STRICT JSON)
{{
  "stage": "clarifying | searching | path_a | path_b | path_c | planning | editing | saved",
  "message": "your reply to show the user",
  "search_params": null or {{
    "task_description": "...",
    "available_inputs": "...",
    "desired_outputs": "..."
  }},
  "search_results": null,
  "selected_agent_id": null,
  "execution_mode": null,
  "execution_input": null,
  "composition_agents": null,
  "draft": null or {{
    "name": "Agent name",
    "description": "One-line description",
    "steps": [
      {{
        "stepId": "unique-id",
        "order": 1,
        "type": "llm",
        "systemPrompt": "...",
        "inputSchema": [{{"fieldName": "...", "type": "string", "required": true, "description": "..."}}],
        "outputSchema": [{{"fieldName": "...", "type": "string", "required": true, "description": "...", "visibility": "public"}}],
        "readFromBlackboard": ["agent_input.fieldName"]
      }},
      {{
        "stepId": "unique-id-2",
        "order": 2,
        "type": "logic",
        "logicType": "condition",
        "condition": {{"field": "fieldName", "threshold": 0.5, "then": "step-a", "else": "step-b"}}
      }}
    ],
    "inputSchema": [...],
    "outputSchema": [...]
  }}
}}
"""


class AgentChatService:

    def __init__(self) -> None:
        self._session_dao = AgentChatSessionDAO()
        self._agent_dao = AgentDAO()

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        user_id: str,
        message: str,
        session_id: str | None,
        agent_id: str | None,
    ) -> dict[str, Any]:
        """
        Main entry point for POST /agents/chat.
        """
        # 1. Resolve session
        if agent_id and session_id:
            session = self._session_dao.find_by_session_id(agent_id, session_id)
        else:
            session = None

        if session is None:
            agent_record = self._agent_dao.create({
                "name": "Untitled Agent",
                "description": "",
                "steps": [{"order": 1, "type": "llm", "systemPrompt": ""}],
                "authorId": user_id,
            })
            agent_id = agent_record["agentId"]
            session = self._session_dao.create(agent_id, user_id)

        agent_id = session["agentId"]
        session_id = session["sessionId"]

        # 2. Load history
        history: list[dict[str, str]] = list(session.get("history", []))

        # 3. Append user message
        now = datetime.now(timezone.utc).isoformat()
        history.append({"role": "user", "content": message, "timestamp": now})
        self._session_dao.update(
            agent_id=agent_id,
            session_id=session_id,
            created_at=session["createdAt"],
            history=history,
        )

        # 4. Call LLM
        system = self._build_system_prompt()
        llm_messages = [
            {"role": h["role"], "content": h["content"]} for h in history
        ]
        try:
            resp = _llm.messages.create(
                model=_settings.claude_sonnet_model,
                max_tokens=4096,
                system=system,
                messages=llm_messages,
            )
            raw_reply: str = resp.content[0].text
        except Exception as exc:
            return {
                "sessionId": session_id,
                "agentId": agent_id,
                "stage": session.get("stage", "clarifying"),
                "message": f"LLM call failed: {exc}",
                "draft": None,
            }

        # 5. Parse response
        parsed = self._parse_json(raw_reply, default={
            "stage": session.get("stage", "clarifying"),
            "message": raw_reply,
            "draft": None,
        })

        stage: str = parsed.get("stage", session.get("stage", "clarifying"))
        reply_message: str = parsed.get("message", raw_reply)
        draft: dict | None = parsed.get("draft")
        search_params: dict | None = parsed.get("search_params")
        search_results: dict | None = parsed.get("search_results")
        selected_agent_id: str | None = parsed.get("selected_agent_id")
        execution_mode: str | None = parsed.get("execution_mode")
        execution_input: dict | None = parsed.get("execution_input")
        composition_agents: list | None = parsed.get("composition_agents")

        # 6. Handle SEARCHING stage — call search_agents backend
        if stage == "searching" and search_params:
            search_results = self._do_search(search_params)
            # Feed results back to LLM for routing
            routing_result = self._route_search_results(
                history, system, search_params, search_results
            )
            if routing_result:
                parsed = routing_result
                stage = parsed.get("stage", "path_c")
                reply_message = parsed.get("message", "")
                draft = parsed.get("draft")
                search_results = parsed.get("search_results", search_results)
                raw_reply = json.dumps(parsed, ensure_ascii=False)

        # 7. Append assistant reply
        history.append({
            "role": "assistant",
            "content": raw_reply,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 8. Persist session
        self._session_dao.update(
            agent_id=agent_id,
            session_id=session_id,
            created_at=session["createdAt"],
            stage=stage,
            history=history,
        )

        # 9. Auto-save draft
        if draft and draft.get("steps"):
            self._save_draft(agent_id, user_id, draft)

        return {
            "sessionId": session_id,
            "agentId": agent_id,
            "stage": stage,
            "message": reply_message,
            "draft": draft,
            "searchResults": search_results,
            "selectedAgentId": selected_agent_id,
            "executionMode": execution_mode,
            "executionInput": execution_input,
            "compositionAgents": composition_agents,
        }

    # ── Search integration ────────────────────────────────────────────────────

    def _do_search(self, search_params: dict[str, Any]) -> dict[str, Any]:
        """
        Call the search backend. Uses OpenSearch if configured,
        falls back to DDB keyword search.
        """
        if _settings.opensearch_endpoint:
            return self._opensearch_search(search_params)
        return self._fallback_search(search_params)

    def _opensearch_search(self, search_params: dict[str, Any]) -> dict[str, Any]:
        """Vector search via MCP gateway tools."""
        try:
            from mcp_gateway.tools.search import search_agents
            return search_agents(
                task_description=search_params.get("task_description", ""),
                available_inputs=search_params.get("available_inputs", ""),
                desired_outputs=search_params.get("desired_outputs", ""),
            )
        except Exception:
            return self._fallback_search(search_params)

    def _fallback_search(self, search_params: dict[str, Any]) -> dict[str, Any]:
        """Keyword-based fallback when OpenSearch is not configured."""
        keyword = search_params.get("task_description", "")
        if not keyword:
            return {"path": "no_results", "results": [], "categories": []}

        all_results = self._agent_dao.search(keyword)
        if not all_results:
            return {"path": "no_results", "results": [], "categories": []}

        # Simulate scoring based on keyword match quality
        results = []
        for agent in all_results[:20]:
            results.append({
                "agent_id": agent.get("agentId", ""),
                "name": agent.get("name", ""),
                "description": agent.get("description", ""),
                "category": agent.get("category", ""),
                "score": 0.75,  # placeholder score for keyword search
            })

        if results:
            return {"path": "indirect", "results": results, "categories": []}
        return {"path": "no_results", "results": [], "categories": []}

    def _route_search_results(
        self,
        history: list[dict],
        system: str,
        search_params: dict,
        search_results: dict,
    ) -> dict[str, Any] | None:
        """
        Feed search results back to LLM for path routing.
        """
        routing_message = (
            f"Search completed. Results:\n"
            f"Path: {search_results.get('path', 'no_results')}\n"
            f"Results: {json.dumps(search_results.get('results', [])[:5], ensure_ascii=False)}\n"
            f"Categories: {json.dumps(search_results.get('categories', [])[:5], ensure_ascii=False)}\n\n"
            f"Route the user to the appropriate path based on these results."
        )

        messages = [
            {"role": h["role"], "content": h["content"]} for h in history
        ]
        messages.append({"role": "user", "content": routing_message})

        try:
            resp = _llm.messages.create(
                model=_settings.claude_sonnet_model,
                max_tokens=4096,
                system=system,
                messages=messages,
            )
            raw = resp.content[0].text
            parsed = self._parse_json(raw, default=None)
            if parsed:
                parsed["search_results"] = search_results
            return parsed
        except Exception:
            return None

    # ── Draft persistence ─────────────────────────────────────────────────────

    def _save_draft(self, agent_id: str, user_id: str, draft: dict) -> str:
        steps = draft.get("steps", [])
        for i, s in enumerate(steps):
            if "order" not in s:
                s["order"] = i + 1
            if "type" not in s:
                s["type"] = "llm"

        data: dict[str, Any] = {
            "name": draft.get("name", "Untitled Agent"),
            "description": draft.get("description", ""),
            "steps": steps,
            "inputSchema": draft.get("inputSchema", []),
            "outputSchema": draft.get("outputSchema", []),
        }

        existing = self._agent_dao.get(agent_id)
        if existing and existing.get("status") == "published":
            self._agent_dao.save_draft(agent_id, data)
        elif existing:
            self._agent_dao.update(agent_id, "LATEST", data)
        return agent_id

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    @staticmethod
    def _parse_json(text: str, default: dict[str, Any] | None) -> dict[str, Any] | None:
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        return default
