"""
RunService — Agent execution engine with Blackboard Pattern.

Blackboard
----------
A shared key-value store per run. Every step reads declared fields from
the blackboard and writes its output back after execution.

  agent_input           → the input passed to the agent by the caller
  step_{stepId}_output  → each step's validated output

Steps declare which fields they need via `readFromBlackboard`.
Each step outputs to its own `outputSchema` — no runtime override.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import anthropic
import boto3
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.dao.agent_dao import AgentDAO

_settings = get_settings()
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)
_lambda_client = boto3.client("lambda", region_name=_settings.aws_region)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _invoke_agent_lambda(
    agent_id: str,
    version: str,
    system_prompt: str,
    output_schema: list,
    input_data: dict,
) -> dict[str, Any]:
    """Invoke the shared agent-executor Lambda synchronously."""
    payload_bytes = json.dumps({
        "agentId": agent_id,
        "version": version,
        "systemPrompt": system_prompt,
        "outputSchema": output_schema,
        "input": input_data,
    }).encode()
    resp = _lambda_client.invoke(
        FunctionName=_settings.lambda_agent_executor_arn,
        InvocationType="RequestResponse",
        Payload=payload_bytes,
    )
    raw = resp["Payload"].read()
    if resp.get("FunctionError"):
        err = json.loads(raw)
        raise RuntimeError(f"Lambda error: {err.get('errorMessage', 'unknown')}")
    result = json.loads(raw)
    if result.get("error"):
        raise RuntimeError(f"Agent error: {result['error']}")
    return result.get("output", {})


# ── Blackboard helpers ────────────────────────────────────────────────────────

def _get_nested(blackboard: dict, dot_path: str) -> Any:
    """
    Resolve a dot-path reference into the blackboard.
    e.g. "step_1_output.competitors" → blackboard["step_1_output"]["value"]["competitors"]
    e.g. "agent_input.topic" → blackboard["agent_input"]["value"]["topic"]
    """
    parts = dot_path.split(".", 1)
    key = parts[0]
    entry = blackboard.get(key)
    if not entry:
        return None
    value = entry.get("value", {})
    if len(parts) == 1:
        return value
    # Drill into the value dict
    field = parts[1]
    if isinstance(value, dict):
        return value.get(field)
    return None


def _extract_blackboard_fields(
    blackboard: dict, read_from: list[str],
) -> dict[str, Any]:
    """Extract only the declared fields from the blackboard."""
    fields: dict[str, Any] = {}
    for path in read_from:
        val = _get_nested(blackboard, path)
        if val is not None:
            fields[path] = val
    return fields


def _validate_output(output: dict, schema: list[dict]) -> list[str]:
    """
    Validate output against the step's outputSchema.
    Returns a list of error messages (empty = valid).
    Checks: required fields present, basic type matching.
    """
    errors: list[str] = []
    for field in schema:
        fname = field.get("fieldName", "")
        required = field.get("required", True)
        expected_type = field.get("type", "").lower()

        if fname not in output:
            if required:
                errors.append(f"Missing required field: {fname}")
            continue

        val = output[fname]

        # Basic type checks
        if expected_type in ("string",) and not isinstance(val, str):
            errors.append(f"Field '{fname}' expected string, got {type(val).__name__}")
        elif expected_type in ("number", "integer") and not isinstance(val, (int, float)):
            errors.append(f"Field '{fname}' expected number, got {type(val).__name__}")
        elif expected_type in ("boolean", "bool") and not isinstance(val, bool):
            errors.append(f"Field '{fname}' expected boolean, got {type(val).__name__}")
        elif expected_type in ("array", "list", "list<string>") and not isinstance(val, list):
            errors.append(f"Field '{fname}' expected array, got {type(val).__name__}")
        elif expected_type in ("object", "map", "dict") and not isinstance(val, dict):
            errors.append(f"Field '{fname}' expected object, got {type(val).__name__}")

    return errors


class RunService:

    def __init__(self) -> None:
        self._agent_dao = AgentDAO()

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger_run(self, agent_id: str, triggered_by: str) -> dict[str, Any]:
        """Validate the agent, create a run record, return immediately."""
        agent = self._get_agent_or_404(agent_id)
        self._assert_owner(agent, triggered_by)

        steps = agent.get("steps", [])
        if not steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent has no steps to execute",
            )
        if len(steps) > _settings.orchestrator_max_steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent exceeds the maximum step limit ({_settings.orchestrator_max_steps})",
            )

        from app.services.agent_service import AgentService
        validation = AgentService()._run_validation(agent)
        if not validation["compatible"]:
            issues_str = "; ".join(
                f"{i['stepId']}.{i['field']}: {i['issue']}"
                for i in validation["issues"]
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent validation failed: {issues_str}",
            )

        return self._agent_dao.create_run(agent_id, triggered_by)

    def execute_run(
        self, agent_id: str, run_id: str, triggered_by: str,
        agent_input: dict[str, Any] | None = None,
    ) -> None:
        """Execute all agent steps with blackboard. Runs inside a BackgroundTask."""
        try:
            agent = self._agent_dao.get(agent_id)
            if not agent:
                return
            run = self._find_run(agent_id, run_id)
            if not run:
                return
            steps = sorted(agent.get("steps", []), key=lambda s: s.get("order", 0))
            context = self._resolve_context(agent.get("context", {}), triggered_by)

            # Initialize blackboard with agent input
            blackboard: dict[str, Any] = {}
            blackboard["agent_input"] = {
                "value": agent_input or {},
                "writtenAt": _now(),
            }

            self._execute_steps(
                agent_id=agent_id,
                run_id=run_id,
                started_at=run["startedAt"],
                steps=steps,
                context=context,
                blackboard=blackboard,
                existing_results=[],
            )
        except Exception as exc:
            try:
                run = self._find_run(agent_id, run_id)
                if run:
                    self._agent_dao.update_run_status(
                        agent_id, run_id, run["startedAt"], "failed",
                        finished=True, extra={"fatalError": str(exc)},
                    )
            except Exception:
                pass

    def resume_run(
        self, agent_id: str, run_id: str, requester_id: str, answer: Any,
    ) -> dict[str, Any]:
        """Inject user answer into paused step, flip to running."""
        agent = self._get_agent_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        run = self._find_run_or_404(agent_id, run_id)
        if run["status"] != "waiting_user_input":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Run is not paused (current status: {run['status']})",
            )
        pending_step_id: str = run.get("pendingStepId", "")
        step_results: list[dict] = list(run.get("stepResults", []))
        for i, sr in enumerate(step_results):
            if sr.get("stepId") == pending_step_id:
                output_field: str = sr.get("outputField") or "answer"
                step_results[i] = {
                    **sr, "status": "success",
                    "output": {output_field: answer}, "pendingQuestion": None,
                }
                break
        self._agent_dao.update_run_status(
            agent_id, run_id, run["startedAt"], "running",
            step_results=step_results,
        )
        return self._find_run_or_404(agent_id, run_id)

    def continue_run(self, agent_id: str, run_id: str, triggered_by: str) -> None:
        """Continue from after the paused step."""
        try:
            agent = self._agent_dao.get(agent_id)
            if not agent:
                return
            run = self._find_run(agent_id, run_id)
            if not run:
                return
            pending_step_order: int = run.get("pendingStepOrder", 0)
            remaining = sorted(
                [s for s in agent["steps"] if s.get("order", 0) > pending_step_order],
                key=lambda s: s.get("order", 0),
            )
            context = self._resolve_context(agent.get("context", {}), triggered_by)
            blackboard = run.get("blackboard", {})
            self._execute_steps(
                agent_id=agent_id, run_id=run_id, started_at=run["startedAt"],
                steps=remaining, context=context, blackboard=blackboard,
                existing_results=list(run.get("stepResults", [])),
            )
        except Exception as exc:
            try:
                run = self._find_run(agent_id, run_id)
                if run:
                    self._agent_dao.update_run_status(
                        agent_id, run_id, run["startedAt"], "failed",
                        finished=True, extra={"fatalError": str(exc)},
                    )
            except Exception:
                pass

    def get_run(self, agent_id: str, run_id: str, requester_id: str) -> dict[str, Any]:
        agent = self._get_agent_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        return self._find_run_or_404(agent_id, run_id)

    def list_runs(self, agent_id: str, requester_id: str, limit: int = 20) -> dict[str, Any]:
        agent = self._get_agent_or_404(agent_id)
        self._assert_owner(agent, requester_id)
        all_runs = self._agent_dao.get_runs(agent_id, limit=limit)
        runs = [r for r in all_runs if r.get("triggeredBy") == requester_id]
        return {"runs": runs, "total": len(runs)}

    # ── Run lookup helpers ────────────────────────────────────────────────────

    def _find_run(self, agent_id: str, run_id: str) -> dict[str, Any] | None:
        runs = self._agent_dao.get_runs(agent_id, limit=50)
        return next((r for r in runs if r.get("runId") == run_id), None)

    def _find_run_or_404(self, agent_id: str, run_id: str) -> dict[str, Any]:
        run = self._find_run(agent_id, run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        return run

    # ── Core execution loop (Blackboard Pattern) ──────────────────────────────

    def _execute_steps(
        self,
        agent_id: str,
        run_id: str,
        started_at: str,
        steps: list[dict],
        context: dict,
        blackboard: dict[str, Any],
        existing_results: list[dict],
    ) -> dict[str, Any]:
        all_results: list[dict] = list(existing_results)

        # Persist initial blackboard state
        self._save_blackboard(agent_id, run_id, started_at, blackboard)

        for step in steps:
            t0 = time.monotonic()

            # 1. Extract declared fields from blackboard
            read_from = step.get("readFromBlackboard", [])
            bb_fields = _extract_blackboard_fields(blackboard, read_from)

            # 2. Get the step's own outputSchema
            output_schema = step.get("outputSchema", [])

            # 3. Execute with retry
            max_retries = _settings.step_max_retries
            last_error: str = ""
            result: dict[str, Any] | None = None

            for attempt in range(1 + max_retries):
                try:
                    result = self._execute_single_step(
                        step, context, bb_fields, output_schema,
                    )
                    if result["status"] != "failed":
                        break
                    last_error = result.get("error", "")
                except Exception as exc:
                    last_error = str(exc)
                    result = {
                        "stepId": step.get("stepId", ""),
                        "type": step.get("type", ""),
                        "status": "failed",
                        "error": last_error,
                        "input": {},
                        "output": {},
                    }
                if attempt < max_retries:
                    time.sleep(_settings.step_retry_delay_seconds)

            assert result is not None
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            all_results.append(result)

            if result["status"] == "failed":
                self._agent_dao.update_run_status(
                    agent_id, run_id, started_at, "failed",
                    step_results=all_results, finished=True,
                    extra={"blackboard": blackboard},
                )
                return self._find_run_or_404(agent_id, run_id)

            if result["status"] == "waiting_user_input":
                self._agent_dao.update_run_status(
                    agent_id, run_id, started_at, "waiting_user_input",
                    step_results=all_results,
                    extra={
                        "pendingStepId": step.get("stepId", ""),
                        "pendingStepOrder": step.get("order", 0),
                        "blackboard": blackboard,
                    },
                )
                return self._find_run_or_404(agent_id, run_id)

            # 4. Validate output against step's own outputSchema
            output = result.get("output", {})
            if output_schema:
                errors = _validate_output(output, output_schema)
                if errors:
                    result["validationWarnings"] = errors
                    # Don't fail — just warn. Output still written to blackboard.

            # 5. Write to blackboard
            step_id = step.get("stepId", "")
            bb_key = f"step_{step_id}_output"
            bb_entry: dict[str, Any] = {
                "value": output,
                "writtenBy": step_id,
                "writtenAt": _now(),
            }
            # For agent steps, include public blackboard from inner execution
            if result.get("publicBlackboard"):
                bb_entry["publicBlackboard"] = result["publicBlackboard"]
            blackboard[bb_key] = bb_entry

            # 6. Persist blackboard after each step
            self._save_blackboard(agent_id, run_id, started_at, blackboard)

        # All steps done
        self._agent_dao.update_run_status(
            agent_id, run_id, started_at, "success",
            step_results=all_results, finished=True,
            extra={"blackboard": blackboard},
        )
        try:
            self._agent_dao.update_last_used(agent_id)
        except Exception:
            pass
        return self._find_run_or_404(agent_id, run_id)

    def _save_blackboard(
        self, agent_id: str, run_id: str, started_at: str, blackboard: dict,
    ) -> None:
        """Persist the current blackboard state to the run record."""
        self._agent_dao.update_run_status(
            agent_id, run_id, started_at, "running",
            extra={"blackboard": blackboard},
        )

    def _execute_single_step(
        self, step: dict, context: dict, bb_fields: dict[str, Any],
        output_schema: list[dict],
    ) -> dict[str, Any]:
        step_type = step.get("type", "").lower()
        if step_type == "llm":
            return self._exec_llm(step, context, bb_fields, output_schema)
        if step_type == "agent":
            return self._exec_agent(step, context, bb_fields, output_schema)
        raise ValueError(f"Unknown step type: {step_type!r}")

    # ── Step executors ────────────────────────────────────────────────────────

    def _exec_llm(
        self, step: dict, context: dict, bb_fields: dict[str, Any],
        output_schema: list[dict],
    ) -> dict[str, Any]:
        prompt = step.get("systemPrompt", "") or step.get("prompt", "")

        # Build user message from blackboard fields
        if bb_fields:
            user_content = json.dumps(bb_fields, ensure_ascii=False, indent=2)
        else:
            user_content = "No input provided."

        kwargs: dict[str, Any] = {
            "model": _settings.claude_sonnet_model,
            "max_tokens": 2048,
            "system": prompt,
            "messages": [{"role": "user", "content": user_content}],
        }

        # Tell LLM to output in the step's own outputSchema format
        if output_schema and isinstance(output_schema, list) and output_schema:
            hint = {
                f.get("fieldName", "result"): f.get("type", "string")
                for f in output_schema
            }
            kwargs["system"] = (
                f"{prompt}\n\n"
                f"Respond with valid JSON matching this schema: "
                f"{json.dumps(hint, ensure_ascii=False)}"
            )

        resp = _llm.messages.create(**kwargs)
        raw: str = resp.content[0].text

        if output_schema:
            try:
                output = json.loads(raw)
            except json.JSONDecodeError:
                output = {"raw": raw}
        else:
            output = {"content": raw}

        return {
            "stepId": step["stepId"],
            "type": "llm",
            "status": "success",
            "input": bb_fields,
            "output": output,
            "error": None,
        }

    def _exec_agent(
        self, step: dict, context: dict, bb_fields: dict[str, Any],
        output_schema: list[dict],
    ) -> dict[str, Any]:
        ref_agent_id: str = step["agentId"]
        ref_agent = self._agent_dao.get(ref_agent_id)
        if not ref_agent:
            raise ValueError(f"Referenced agent '{ref_agent_id}' not found")

        ref_steps = ref_agent.get("steps", [])
        llm_step = next((s for s in ref_steps if s.get("type") == "llm"), None)
        system_prompt = llm_step.get("systemPrompt", "") if llm_step else ""

        # Build input from blackboard fields mapped to the agent's inputSchema
        input_data: dict[str, Any] = {}
        for field in ref_agent.get("inputSchema", []):
            fname = field["fieldName"]
            # Check if any blackboard field matches this input field name
            for bb_path, bb_val in bb_fields.items():
                if bb_path.endswith(f".{fname}") or bb_path == fname:
                    input_data[fname] = bb_val
                    break
            if fname not in input_data and field.get("default") is not None:
                input_data[fname] = field["default"]

        # Use the step's own outputSchema for the agent call
        effective_schema = output_schema or ref_agent.get("outputSchema", [])

        output = _invoke_agent_lambda(
            agent_id=ref_agent_id,
            version=ref_agent.get("version", "LATEST"),
            system_prompt=system_prompt,
            output_schema=effective_schema,
            input_data=input_data,
        )

        # Collect public fields from the referenced agent's outputSchema
        public_blackboard: dict[str, Any] = {}
        for field in ref_agent.get("outputSchema", []):
            if field.get("visibility") == "public" and field["fieldName"] in output:
                public_blackboard[field["fieldName"]] = output[field["fieldName"]]

        try:
            self._agent_dao.increment_call_count(ref_agent_id)
            self._agent_dao.update_last_used(ref_agent_id)
        except Exception:
            pass

        return {
            "stepId": step["stepId"],
            "type": "agent",
            "status": "success",
            "input": input_data,
            "output": output,
            "publicBlackboard": public_blackboard,
            "error": None,
        }

    # ── Context resolution ────────────────────────────────────────────────────

    def _resolve_context(self, context_template: dict, triggered_by: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        resolved: dict[str, Any] = {}
        for key, val in context_template.items():
            if val == "{{current_user.id}}":
                resolved[key] = triggered_by
            elif val == "{{now}}":
                resolved[key] = now
            else:
                resolved[key] = val
        return resolved

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def _get_agent_or_404(self, agent_id: str) -> dict[str, Any]:
        agent = self._agent_dao.get(agent_id)
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
