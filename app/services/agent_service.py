"""
AgentService — business logic for the Agent module.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.dao.agent_dao import AgentDAO
from app.models.agent import AgentCreateRequest, AgentUpdateRequest

_settings = get_settings()
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)


def _schemas_to_ddb(schemas: list) -> list[dict[str, Any]]:
    """Serialize FieldSchema objects to DDB-safe dicts (strip None values)."""
    result = []
    for s in schemas:
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        result.append({k: v for k, v in d.items() if v is not None})
    return result


def _steps_to_ddb(steps: list) -> list[dict[str, Any]]:
    """Serialize Step objects to DDB-safe dicts (strip None values)."""
    result = []
    for s in steps:
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        # Recursively strip None from nested schema lists
        if "inputSchema" in d:
            d["inputSchema"] = [{k: v for k, v in f.items() if v is not None}
                                for f in (d["inputSchema"] or [])]
        if "outputSchema" in d:
            d["outputSchema"] = [{k: v for k, v in f.items() if v is not None}
                                 for f in (d["outputSchema"] or [])]
        result.append({k: v for k, v in d.items() if v is not None})
    return result


class AgentService:

    def __init__(self) -> None:
        self._dao = AgentDAO()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_404(self, agent_id: str) -> dict[str, Any]:
        agent = self._dao.get(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent '{agent_id}' not found",
            )
        return agent

    @staticmethod
    def _assert_owner(agent: dict[str, Any], requester_id: str) -> None:
        if agent["authorId"] != requester_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this agent",
            )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, author_id: str, body: AgentCreateRequest) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": body.name,
            "description": body.description,
            "steps": _steps_to_ddb(body.steps),
            "inputSchema": _schemas_to_ddb(body.inputSchema),
            "outputSchema": _schemas_to_ddb(body.outputSchema),
            "visibility": body.visibility,
            "toolsRequired": body.toolsRequired,
            "authorId": author_id,
        }
        return self._dao.create(data)

    def get(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        return agent

    def update(
        self, agent_id: str, requester_id: str, body: AgentUpdateRequest
    ) -> dict[str, Any]:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        fields: dict[str, Any] = body.model_dump(exclude_none=True)

        if body.steps is not None:
            fields["steps"] = _steps_to_ddb(body.steps)
        if body.inputSchema is not None:
            fields["inputSchema"] = _schemas_to_ddb(body.inputSchema)
        if body.outputSchema is not None:
            fields["outputSchema"] = _schemas_to_ddb(body.outputSchema)

        if not fields:
            return agent

        updated = self._dao.update(agent_id, agent["version"], fields)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return updated

    def delete(self, agent_id: str, requester_id: str) -> None:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        self._dao.delete(agent_id, agent["version"])

    # ── Business actions ──────────────────────────────────────────────────────

    def publish(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        if agent["status"] == "published":
            return agent

        updated = self._dao.update(
            agent_id,
            agent["version"],
            {"status": "published", "visibility": "public"},
        )
        return updated  # type: ignore[return-value]

    def test(
        self,
        agent_id: str,
        requester_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Test the agent with sample input.
        Only works for simple agents (single type=llm step).
        systemPrompt is read from the first llm step.
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        steps: list[dict] = agent.get("steps", [])
        llm_step = next((s for s in steps if s.get("type") == "llm"), None)
        if not llm_step:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent has no LLM step — only simple agents (type=llm) can be tested here",
            )

        system_prompt: str = llm_step.get("systemPrompt", "")
        output_schema: list = llm_step.get("outputSchema") or agent.get("outputSchema", [])

        if output_schema:
            schema_hint = {f["fieldName"]: f["type"] for f in output_schema}
            system_prompt = (
                f"{system_prompt}\n\n"
                f"Respond with valid JSON that matches exactly this schema: "
                f"{json.dumps(schema_hint, ensure_ascii=False)}"
            )

        t0 = time.monotonic()
        response = _llm.messages.create(
            model=_settings.claude_haiku_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw: str = response.content[0].text
        try:
            output = json.loads(raw)
        except json.JSONDecodeError:
            output = {"raw": raw}

        return {"output": output, "latency_ms": latency_ms}

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_mine(self, author_id: str) -> list[dict[str, Any]]:
        return self._dao.list_by_author(author_id)
