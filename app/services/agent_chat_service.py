"""
AgentChatService — POST /agents/chat

Replaces the old OrchestratorService with a session-backed, 4-stage
LLM-driven agent creation flow:

  CLARIFYING  → ask 2-3 follow-up questions to understand requirements
  CONFIRMING  → summarise requirements as bullet points, ask user to confirm
  PLANNING    → generate agent draft (simple or composite) with steps
  EDITING     → apply user modifications to the existing draft

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


# ── System prompt that drives the 4-stage state machine ──────────────────────

_SYSTEM_PROMPT = """\
You are an AI Agent designer. You help users create AI Agents through a \
structured conversation. You MUST follow the stage-based protocol below \
and ALWAYS respond with strict JSON — no markdown, no explanation outside \
the JSON.

## Stages

### CLARIFYING
- Ask 2-3 focused follow-up questions to fully understand the user's needs.
- Never assume what the user wants.
- Stay in this stage until requirements are clear enough to summarise.

### CONFIRMING
- Summarise the requirements as a bullet-point list.
- Ask the user to confirm: "Is this correct?"
- If the user corrects something, update and re-confirm.
- Move to PLANNING only after explicit confirmation.

### PLANNING
- Decide whether the task can be done in one LLM call (Simple Agent) or \
needs multiple steps (Composite Agent).
- Simple Agent: generate a single step with type="llm" and a systemPrompt.
- Composite Agent: generate multiple steps. Each step is either:
    type="llm" (with systemPrompt, inputSchema, outputSchema)
    type="agent" (with agentId referencing a marketplace agent, plus outputSchema)

#### Step selection — pick whatever works best:
1. For each step, check if a marketplace agent fits:
   - Does it do exactly what this step needs?
   - Does it have a high callCount (proven, reliable)?
   - Does it have tool access or capabilities that a raw LLM prompt cannot replicate?
   - Has an expert built a better version of this task in the marketplace?
   If YES to any of these → use type="agent" with its agentId.

2. If no marketplace agent fits well, create a custom type="llm" step.

#### Blackboard — context sharing between steps:
Steps share data through a blackboard (shared key-value store).
At runtime, agent input is written as "agent_input" and each step's output \
is written as "step_{{stepId}}_output".

For EVERY step you MUST generate:

1. outputSchema — MANDATORY for all steps (not just the last one).
   Each field must have: fieldName, type, required, description, visibility.
   visibility is either "public" (visible to outer agents that call this one) \
   or "private" (internal only, default).
   Set visibility="public" for fields that would be useful to outer composite agents.
   Set visibility="private" for intermediate/debug fields.

2. readFromBlackboard — a list of dot-path references declaring which \
   blackboard fields this step needs as input.
   Format: "agent_input.fieldName" or "step_{{prevStepId}}_output.fieldName"
   The first step typically reads from "agent_input.*".
   Subsequent steps read from prior steps' outputs.
   Only declare fields the step actually needs — saves tokens at runtime.

3. Do NOT generate transformMode — it is removed.

- Return the full draft in the "draft" field.

### EDITING
- The user may request changes to the draft via chat.
- Apply the requested modifications and return the updated draft.
- Stay in EDITING until the user says they are satisfied or wants to save.
- When the user explicitly says to save/publish, move to SAVED.

### SAVED
- Confirm the agent has been saved. No further changes.

## Available marketplace agents
{marketplace_agents}

## Response format (STRICT JSON, nothing else)
{{
  "stage": "clarifying | confirming | planning | editing | saved",
  "message": "your reply to show the user",
  "draft": null or {{
    "name": "Agent name",
    "description": "One-line description",
    "steps": [
      {{
        "order": 1,
        "type": "llm",
        "systemPrompt": "...",
        "inputSchema": [{{"fieldName": "...", "type": "string", "required": true, "description": "..."}}],
        "outputSchema": [{{"fieldName": "...", "type": "string", "required": true, "description": "...", "visibility": "public"}}],
        "readFromBlackboard": ["agent_input.fieldName"]
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

        1. Get or create session (DDB)
        2. Load history from session
        3. Append user message
        4. Call LLM with full history + system prompt
        5. Parse LLM response (stage, message, draft)
        6. Append assistant reply to history
        7. Persist updated session to DDB
        8. Return { sessionId, agentId, stage, message, draft }
        """

        # 1. Resolve session
        if agent_id and session_id:
            session = self._session_dao.find_by_session_id(agent_id, session_id)
        else:
            session = None

        if session is None:
            # New conversation — create a real agent record immediately
            # so it shows up on "My Agents" and can be resumed.
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

        # 3. Append user message and persist immediately — so it's not lost
        #    if the LLM call fails
        now = datetime.now(timezone.utc).isoformat()
        history.append({
            "role": "user",
            "content": message,
            "timestamp": now,
        })
        self._session_dao.update(
            agent_id=agent_id,
            session_id=session_id,
            created_at=session["createdAt"],
            history=history,
        )

        # 4. Build system prompt with marketplace agents
        system = self._build_system_prompt()

        # 5. Call LLM with full conversation history
        llm_messages = [
            {"role": h["role"], "content": h["content"]}
            for h in history
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
            # LLM call failed — user message is already saved.
            # Return the error so the frontend can display it.
            return {
                "sessionId": session_id,
                "agentId": agent_id,
                "stage": session.get("stage", "clarifying"),
                "message": f"LLM call failed: {exc}",
                "draft": None,
            }

        # 6. Parse structured response
        parsed = self._parse_json(raw_reply, default={
            "stage": session.get("stage", "clarifying"),
            "message": raw_reply,
            "draft": None,
        })

        stage: str = parsed.get("stage", session.get("stage", "clarifying"))
        reply_message: str = parsed.get("message", raw_reply)
        draft: dict | None = parsed.get("draft")

        # 7. Append assistant reply to history
        history.append({
            "role": "assistant",
            "content": raw_reply,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 8. Persist session to DDB
        self._session_dao.update(
            agent_id=agent_id,
            session_id=session_id,
            created_at=session["createdAt"],
            stage=stage,
            history=history,
        )

        # 9. Auto-save draft to DDB as a real agent record
        if draft and draft.get("steps"):
            self._save_draft(agent_id, user_id, draft)

        return {
            "sessionId": session_id,
            "agentId": agent_id,
            "stage": stage,
            "message": reply_message,
            "draft": draft,
        }

    def _save_draft(self, agent_id: str, user_id: str, draft: dict) -> str:
        """
        Update the agent record in DDB with the latest draft content.
        The agent record already exists (created at session start).
        """
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
        """Inject marketplace agents into the system prompt."""
        agents = self._agent_dao.list_all_marketplace()
        agent_summaries = json.dumps(
            [
                {
                    "agentId": a.get("agentId"),
                    "name": a.get("name"),
                    "description": a.get("description"),
                    "inputSchema": a.get("inputSchema", []),
                    "outputSchema": a.get("outputSchema", []),
                }
                for a in agents[:30]  # cap to avoid blowing context window
            ],
            ensure_ascii=False,
            indent=2,
        )
        return _SYSTEM_PROMPT.format(marketplace_agents=agent_summaries)

    @staticmethod
    def _parse_json(text: str, default: dict[str, Any]) -> dict[str, Any]:
        """Robustly extract the first JSON object from an LLM response."""
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
