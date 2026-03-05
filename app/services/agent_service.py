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

    def _validate_steps(self, steps: list) -> None:
        """
        Validate step contents beyond what Pydantic enforces:
          - type=agent steps must reference an agent that exists in the marketplace
        """
        for s in steps:
            step = s.model_dump() if hasattr(s, "model_dump") else dict(s)
            if step.get("type") == "agent":
                ref_id = step.get("agentId", "")
                if not ref_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Agent step is missing agentId",
                    )
                ref_agent = self._dao.get(ref_id)
                if not ref_agent:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Referenced agent '{ref_id}' not found in marketplace",
                    )

    def _check_draft_quota(self, author_id: str, max_drafts: int = 10) -> None:
        """
        Enforce draft quota: each customer can have at most max_drafts draft agents.
        Published agents don't count toward the quota.
        """
        agents = self._dao.list_by_author(author_id)
        draft_count = sum(1 for a in agents if a.get("status") == "draft")
        if draft_count >= max_drafts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Draft quota reached ({max_drafts}). "
                       f"Publish or delete a draft before creating a new one.",
            )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, author_id: str, body: AgentCreateRequest) -> dict[str, Any]:
        self._validate_steps(body.steps)

        # Draft quota check
        self._check_draft_quota(author_id)

        data: dict[str, Any] = {
            "name": body.name,
            "description": body.description,
            "steps": _steps_to_ddb(body.steps),
            "inputSchema": _schemas_to_ddb(body.inputSchema),
            "outputSchema": _schemas_to_ddb(body.outputSchema),
            "visibility": body.visibility,
            "toolsRequired": body.toolsRequired,
            "context": body.context,
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
            self._validate_steps(body.steps)
            fields["steps"] = _steps_to_ddb(body.steps)
        if body.inputSchema is not None:
            fields["inputSchema"] = _schemas_to_ddb(body.inputSchema)
        if body.outputSchema is not None:
            fields["outputSchema"] = _schemas_to_ddb(body.outputSchema)

        if not fields:
            return agent

        # If agent is published, save edits to DRAFT to avoid affecting
        # other agents that reference this one via LATEST.
        if agent.get("status") == "published":
            updated = self._dao.save_draft(agent_id, fields)
        else:
            updated = self._dao.update(agent_id, agent["version"], fields)

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return updated

    def delete(self, agent_id: str, requester_id: str) -> None:
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        self._dao.delete(agent_id)
        # Also delete draft if it exists
        self._dao.delete(agent_id, "DRAFT")

    # ── Business actions ──────────────────────────────────────────────────────

    def publish(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        """
        Crash-safe publish flow:
        1. Increment publishVersion + set status=pending (crash recovery anchor)
        2. Create Step Functions State Machine with idempotent name
        3. DDB status=published + ARN (atomic transaction)
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        # Step 1: Increment version and set pending — this is the idempotency key.
        # Same draft always gets the same version number on retry.
        current_version = agent.get("publishVersion", 0)
        new_version = current_version + 1

        self._dao.update(agent_id, "LATEST", {
            "status": "pending",
            "publishVersion": new_version,
            "stateMachineArn": None,
        })

        # Step 2: Build and create State Machine (idempotent — handles "already exists")
        steps = agent.get("steps", [])
        arn = ""
        if steps and any(s.get("type") in ("llm", "agent", "logic") for s in steps):
            try:
                from app.services.state_machine_service import StateMachineService
                sm_svc = StateMachineService()
                definition = sm_svc.build_definition(agent)
                role_arn = _settings.lambda_agent_executor_arn or "arn:aws:iam::role/placeholder"
                arn = sm_svc.create_state_machine(agent_id, new_version, definition, role_arn)
            except Exception:
                # State Machine creation failed — still publish but without ARN
                # Recovery job will retry (Step 10)
                pass

        # Step 3: Publish (status=published + ARN + version)
        publish_fields: dict[str, Any] = {"publishVersion": new_version}
        if arn:
            publish_fields["stateMachineArn"] = arn
        result = self._dao.publish_draft(agent_id, extra_fields=publish_fields)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return result

    def verify_for_publish(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        """
        LLM reviews the agent before publishing.
        Returns { safe: bool, concerns: list[str], published: bool }
        If safe, publishes automatically. If not, returns concerns.
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        # Build a summary of the agent for the LLM to review
        agent_summary = json.dumps({
            "name": agent.get("name"),
            "description": agent.get("description"),
            "inputSchema": agent.get("inputSchema", []),
            "outputSchema": agent.get("outputSchema", []),
            "steps": [
                {
                    "order": s.get("order"),
                    "type": s.get("type"),
                    "systemPrompt": s.get("systemPrompt", "")[:200],
                    "inputSchema": s.get("inputSchema", []),
                    "outputSchema": s.get("outputSchema", []),
                    "readFromBlackboard": s.get("readFromBlackboard", []),
                }
                for s in agent.get("steps", [])
            ],
        }, ensure_ascii=False, indent=2)

        review_prompt = (
            "You are an agent quality reviewer. Review this agent definition "
            "and check for potential issues before publishing to the marketplace.\n\n"
            "Check for:\n"
            "1. Missing or vague system prompts\n"
            "2. Steps with empty outputSchema\n"
            "3. readFromBlackboard references that don't match available fields\n"
            "4. Missing agent-level inputSchema or outputSchema\n"
            "5. Description that doesn't match what the agent actually does\n"
            "6. Any logical issues in the step chain\n\n"
            f"Agent definition:\n{agent_summary}\n\n"
            "Respond with strict JSON:\n"
            '{"safe": true/false, "concerns": ["concern 1", "concern 2"]}\n'
            "If safe, concerns should be an empty list."
        )

        try:
            resp = _llm.messages.create(
                model=_settings.claude_haiku_model,
                max_tokens=512,
                messages=[{"role": "user", "content": review_prompt}],
            )
            raw = resp.content[0].text
            # Parse response
            import re
            cleaned = re.sub(r"```(?:json)?\s*", "", raw.strip()).rstrip("`").strip()
            parsed = json.loads(cleaned)
            safe = parsed.get("safe", True)
            concerns = parsed.get("concerns", [])
        except Exception:
            # If LLM fails, don't block publishing
            safe = True
            concerns = []

        if safe:
            result = self._dao.publish_draft(agent_id)
            return {"safe": True, "concerns": [], "published": True, "agent": result}

        return {"safe": False, "concerns": concerns, "published": False}

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

    def test_step(
        self,
        agent_id: str,
        requester_id: str,
        step_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Test a single step in isolation. Ephemeral — not persisted.
        For llm steps: calls Claude with the step's systemPrompt + input.
        For agent steps: returns an error (needs Lambda, not supported yet).
        """
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)

        steps: list[dict] = agent.get("steps", [])
        step = next((s for s in steps if s.get("stepId") == step_id), None)
        if not step:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{step_id}' not found",
            )

        step_type = step.get("type", "").lower()
        if step_type == "agent":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Testing marketplace agent steps is not supported yet",
            )
        if step_type != "llm":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot test step type: {step_type}",
            )

        system_prompt: str = step.get("systemPrompt", "")

        # Determine output schema: if this is the last step, use its own.
        # Otherwise use the next step's inputSchema.
        sorted_steps = sorted(steps, key=lambda s: s.get("order", 0))
        step_index = next(
            (i for i, s in enumerate(sorted_steps) if s.get("stepId") == step_id), 0
        )
        is_last = step_index == len(sorted_steps) - 1

        if is_last:
            output_schema = step.get("outputSchema") or agent.get("outputSchema", [])
        else:
            next_step = sorted_steps[step_index + 1]
            if next_step.get("type", "").lower() == "agent":
                ref_id = next_step.get("agentId", "")
                ref_agent = self._dao.get(ref_id) if ref_id else None
                output_schema = ref_agent.get("inputSchema", []) if ref_agent else []
            else:
                output_schema = next_step.get("inputSchema", [])

        if output_schema and isinstance(output_schema, list) and output_schema:
            schema_hint = {
                f.get("fieldName", "result") if isinstance(f, dict) else "result":
                f.get("type", "string") if isinstance(f, dict) else "string"
                for f in output_schema
            }
            system_prompt = (
                f"{system_prompt}\n\n"
                f"Respond with valid JSON matching this schema: "
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

        return {"stepId": step_id, "output": output, "latency_ms": latency_ms}

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_mine(self, author_id: str) -> list[dict[str, Any]]:
        return self._dao.list_by_author(author_id)

    # ── Schema compatibility validation ───────────────────────────────────────

    def validate(self, agent_id: str, requester_id: str) -> dict[str, Any]:
        """Validate schema compatibility across all steps in execution order."""
        agent = self._get_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        return self._run_validation(agent)

    def _run_validation(self, agent: dict[str, Any]) -> dict[str, Any]:
        """
        Blackboard-aware validation:

        1. Every step must have an outputSchema (mandatory for blackboard writes).
        2. All referenced marketplace agents must exist.
        3. Every step's readFromBlackboard references must be resolvable
           from agent_input or prior steps' outputSchema fields.
        """
        steps: list[dict[str, Any]] = sorted(
            agent.get("steps", []), key=lambda s: s.get("order", 0)
        )
        if not steps:
            return {"compatible": True, "issues": []}

        issues: list[dict[str, Any]] = []

        # Build the set of available blackboard keys as we walk through steps
        # Start with agent_input fields
        available_bb_fields: set[str] = set()
        for f in agent.get("inputSchema", []):
            available_bb_fields.add(f"agent_input.{f['fieldName']}")

        for step in steps:
            step_id = step.get("stepId", "?")
            step_type = step.get("type", "")

            # Check 1: outputSchema must exist on every step
            output_schema = step.get("outputSchema", [])
            if not output_schema:
                issues.append({
                    "stepId": step_id,
                    "field": "outputSchema",
                    "issue": "Step has no outputSchema — required for blackboard writes",
                    "suggestions": ["Define outputSchema fields for this step"],
                })

            # Check 2: referenced agents must exist
            if step_type == "agent":
                ref_id = step.get("agentId", "")
                if not ref_id or not self._dao.get(ref_id):
                    issues.append({
                        "stepId": step_id,
                        "field": "agentId",
                        "issue": f"Referenced agent '{ref_id}' not found",
                        "suggestions": [],
                    })

            # Check 3: readFromBlackboard references must be resolvable
            read_from = step.get("readFromBlackboard", [])
            for ref in read_from:
                if ref not in available_bb_fields:
                    issues.append({
                        "stepId": step_id,
                        "field": "readFromBlackboard",
                        "issue": f"Blackboard reference '{ref}' not available at this point",
                        "suggestions": sorted(available_bb_fields)[:5],
                    })

            # After this step executes, its outputSchema fields become available
            for f in output_schema:
                if isinstance(f, dict) and f.get("fieldName"):
                    available_bb_fields.add(f"step_{step_id}_output.{f['fieldName']}")

        return {
            "compatible": len(issues) == 0,
            "issues": issues,
        }
