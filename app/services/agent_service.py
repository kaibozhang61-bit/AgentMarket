"""
AgentService — business logic for the Agent module.

Responsibilities:
  - Ownership / permission checks
  - Data shaping before writing to DDB (strip None values, build safe dicts)
  - LLM call for /test endpoint
  - Status-transition logic for /publish endpoint

The service layer never touches HTTP concerns (no Request / Response / HTTPException
from starlette — only FastAPI's HTTPException is used here because it is a plain
Python exception, not HTTP middleware).
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

# One shared Anthropic client for the process
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)


def _schemas_to_ddb(schemas: list) -> list[dict[str, Any]]:
    """
    Serialize a list of FieldSchema objects (or already-plain dicts) to a
    DynamoDB-safe list, stripping any None values DDB would reject.
    """
    result = []
    for s in schemas:
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
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
            "systemPrompt": body.systemPrompt,
            "inputSchema": _schemas_to_ddb(body.inputSchema),
            "outputSchema": _schemas_to_ddb(body.outputSchema),
            "visibility": body.visibility,
            "toolsRequired": body.toolsRequired,
            "authorId": author_id,
        }
        return self._dao.create(data)

    def get(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        """
        Private management view — only the owner can retrieve via this endpoint.
        Public discovery goes through /marketplace/agents.
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        return agent

    def update(
        self, agent_id: str, requester_id: str, body: AgentUpdateRequest
    ) -> dict[str, Any]:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        # Build update dict — only fields explicitly set in the request
        fields: dict[str, Any] = body.model_dump(exclude_none=True)

        # Re-serialize schema lists to strip nested None values
        if body.inputSchema is not None:
            fields["inputSchema"] = _schemas_to_ddb(body.inputSchema)
        if body.outputSchema is not None:
            fields["outputSchema"] = _schemas_to_ddb(body.outputSchema)

        if not fields:
            return agent  # nothing to update

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
        """
        Transition agent status: draft → published.
        Idempotent: calling publish on an already-published agent is a no-op.
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        if agent["status"] == "published":
            return agent  # already published

        updated = self._dao.update(
            agent_id,
            agent["version"],
            {"status": "published"},
        )
        return updated  # type: ignore[return-value]

    def test(
        self,
        agent_id: str,
        requester_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run the agent against sample input using Claude Haiku.
        Returns the model output and wall-clock latency in ms.
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        system_prompt: str = agent.get("systemPrompt", "")
        output_schema: list = agent.get("outputSchema", [])

        # Append output-format instruction so the model returns parseable JSON
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
            # Model didn't return valid JSON — surface raw text under a key
            output = {"raw": raw}

        return {"output": output, "latency_ms": latency_ms}

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_mine(self, author_id: str) -> list[dict[str, Any]]:
        return self._dao.list_by_author(author_id)
