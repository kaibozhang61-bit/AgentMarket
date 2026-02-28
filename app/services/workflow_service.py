"""
WorkflowService — business logic for the Workflow module.

Responsibilities:
  - Ownership / permission checks
  - Step lifecycle (add / replace / delete)
  - Schema compatibility validation (POST /validate)

Validate logic
--------------
Process steps in `order` sequence, maintaining a running set of
"available field names" that grows as each step produces outputs.
For every AGENT step, check that all required input fields with no
default value can be resolved from one of:
  1. inputMapping          — explicitly mapped by the user
  2. missingFieldsResolution — explicitly resolved by the user
  3. available_fields      — context keys + outputs from prior steps

Issues are collected and returned without short-circuiting so the
caller gets a complete picture in one request.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status

from app.dao.agent_dao import AgentDAO
from app.dao.workflow_dao import WorkflowDAO
from app.models.workflow import (
    StepBody,
    WorkflowCreateRequest,
    WorkflowUpdateRequest,
)


class WorkflowService:

    def __init__(self) -> None:
        self._wf_dao = WorkflowDAO()
        self._agent_dao = AgentDAO()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_404(self, workflow_id: str) -> dict[str, Any]:
        wf = self._wf_dao.get(workflow_id)
        if not wf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found",
            )
        return wf

    @staticmethod
    def _assert_owner(wf: dict[str, Any], requester_id: str) -> None:
        if wf["authorId"] != requester_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this workflow",
            )

    # ── Workflow CRUD ─────────────────────────────────────────────────────────

    def create(self, author_id: str, body: WorkflowCreateRequest) -> dict[str, Any]:
        return self._wf_dao.create(
            {
                "name": body.name,
                "description": body.description,
                "context": body.context,
                "authorId": author_id,
            }
        )

    def get(self, workflow_id: str, requester_id: str) -> dict[str, Any]:
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        return wf

    def update(
        self, workflow_id: str, requester_id: str, body: WorkflowUpdateRequest
    ) -> dict[str, Any]:
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        fields = body.model_dump(exclude_none=True)
        if not fields:
            return wf
        updated = self._wf_dao.update(workflow_id, fields)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return updated

    def delete(self, workflow_id: str, requester_id: str) -> None:
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        self._wf_dao.delete(workflow_id)

    def list_mine(self, author_id: str) -> list[dict[str, Any]]:
        return self._wf_dao.list_by_author(author_id)

    # ── Step management ───────────────────────────────────────────────────────

    def add_step(
        self, workflow_id: str, requester_id: str, step_body: StepBody
    ) -> dict[str, Any]:
        """
        Append a new step to the workflow.
        Assigns a server-generated stepId; order is set by the caller.
        """
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)

        step_data = step_body.model_dump(exclude_none=True)
        step_data["stepId"] = str(uuid.uuid4())

        result = self._wf_dao.add_step(workflow_id, step_data)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return result

    def replace_step(
        self,
        workflow_id: str,
        step_id: str,
        requester_id: str,
        step_body: StepBody,
    ) -> dict[str, Any]:
        """
        Fully replace a step (PUT semantics).
        The stepId is taken from the URL — any stepId in the body is ignored.
        Full replacement prevents stale fields when the step type changes.
        """
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)

        step_data = step_body.model_dump(exclude_none=True)
        step_data["stepId"] = step_id  # authoritative source is the URL param

        result = self._wf_dao.replace_step(workflow_id, step_id, step_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
            )
        return result

    def delete_step(
        self, workflow_id: str, step_id: str, requester_id: str
    ) -> dict[str, Any]:
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)

        # Confirm step exists before attempting deletion
        steps = wf.get("steps", [])
        if not any(s.get("stepId") == step_id for s in steps):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
            )

        result = self._wf_dao.delete_step(workflow_id, step_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        return result

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self, workflow_id: str, requester_id: str) -> dict[str, Any]:
        wf = self._get_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        return self._run_validation(wf)

    def _run_validation(self, wf: dict[str, Any]) -> dict[str, Any]:
        """
        Check schema compatibility across all steps in execution order.

        available_fields grows as each step completes:
          - Starts with workflow context keys
          - AGENT step: adds fields from agent.outputSchema
          - LLM step:   adds outputSchema.fieldName (if defined)
          - LOGIC step: no new fields (branching only)
        """
        steps: list[dict[str, Any]] = sorted(
            wf.get("steps", []), key=lambda s: s.get("order", 0)
        )
        context_keys: set[str] = set(wf.get("context", {}).keys())
        available_fields: set[str] = set(context_keys)  # grows per step

        issues: list[dict[str, Any]] = []

        for step in steps:
            step_id: str = step.get("stepId", "?")
            step_type: str = step.get("type", "")

            if step_type == "AGENT":
                self._validate_agent_step(
                    step, step_id, context_keys, available_fields, issues
                )

            elif step_type == "LLM":
                # LLM steps are always executable; add their output to available fields
                output_schema = step.get("outputSchema")
                if isinstance(output_schema, dict):
                    field_name = output_schema.get("fieldName")
                    if field_name:
                        available_fields.add(field_name)

            # LOGIC steps (condition / transform / user_input) don't produce
            # new named output fields — they control flow only.

        return {
            "compatible": len(issues) == 0,
            "issues": issues,
        }

    def _validate_agent_step(
        self,
        step: dict[str, Any],
        step_id: str,
        context_keys: set[str],
        available_fields: set[str],
        issues: list[dict[str, Any]],
    ) -> None:
        """
        Validate one AGENT step and append to `available_fields` with the
        agent's output fields so subsequent steps can reference them.
        Appends to `issues` for every unresolvable required field.
        """
        agent_id: str = step.get("agentId", "")
        agent_version: str = step.get("agentVersion", "1.0.0")

        agent = self._agent_dao.get(agent_id, agent_version)
        if not agent:
            issues.append(
                {
                    "stepId": step_id,
                    "field": "agentId",
                    "issue": f"Agent '{agent_id}' not found",
                    "suggestions": [],
                }
            )
            return  # can't inspect schema — skip this step's output contribution

        input_mapping: dict = step.get("inputMapping", {})
        missing_resolution: dict = step.get("missingFieldsResolution", {})

        for field in agent.get("inputSchema", []):
            # Optional fields and fields with defaults are always satisfiable
            if not field.get("required", True):
                continue
            if field.get("default") is not None:
                continue

            field_name: str = field["fieldName"]

            if field_name in input_mapping:
                continue  # explicitly mapped
            if field_name in missing_resolution:
                continue  # explicitly resolved
            if field_name in available_fields:
                continue  # available from context or a prior step

            # ── Unresolvable — build helpful suggestions ──────────────────
            suggestions: list[str] = []
            # Context suggestions
            for k in sorted(context_keys):
                suggestions.append(f"context.{k}")
            suggestions.append("fixed_value")

            issues.append(
                {
                    "stepId": step_id,
                    "field": field_name,
                    "issue": "Required field cannot be resolved from upstream",
                    "suggestions": suggestions[:3],
                }
            )

        # Register this agent's outputs so downstream steps can reference them
        for f in agent.get("outputSchema", []):
            available_fields.add(f["fieldName"])
