"""
RunService — Workflow execution engine.

Execution model (MVP)
---------------------
Synchronous, in-process execution inside the HTTP request.
Steps run sequentially in `order` order.  The three step types behave as:

  AGENT   → resolve input templates → invoke Lambda (agent executor)
             → parse JSON output → increment agent callCount
  LLM     → resolve prompt template → call Claude Sonnet → return text / JSON
  LOGIC   → condition : evaluate simple comparison, record branch (linear flow only)
             transform : pass-through (MVP placeholder)
             user_input: pause run, persist state, return waiting_user_input

Resume flow
-----------
POST /runs/{runId}/resume injects the user's answer as the paused step's output,
then resumes execution from the next step.

Template syntax
---------------
  {{context.<key>}}                → workflow.context[key] (after runtime resolution)
  {{<stepId>.output.<field>}}      → output of a completed prior step
  {{current_user.id}} / {{now}}    → special context values resolved at run start
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
from app.dao.workflow_dao import WorkflowDAO
from app.dao.workflow_run_dao import WorkflowRunDAO

_settings = get_settings()
_llm = anthropic.Anthropic(api_key=_settings.anthropic_api_key)
_lambda_client = boto3.client("lambda", region_name=_settings.aws_region)


def _invoke_agent_lambda(
    agent_id: str,
    version: str,
    system_prompt: str,
    output_schema: list,
    input_data: dict,
) -> dict[str, Any]:
    """
    Invoke the shared agent-executor Lambda synchronously.

    Lambda contract
    ---------------
    Input payload:
      { agentId, version, systemPrompt, outputSchema, input }

    Output payload (success):
      { "output": { ... } }

    Output payload (agent-level error):
      { "error": "..." }

    Lambda-level errors (unhandled exceptions) set FunctionError in the response.
    """
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

    raw = resp["Payload"].read()  # StreamingBody — read once

    if resp.get("FunctionError"):
        err = json.loads(raw)
        raise RuntimeError(f"Lambda error: {err.get('errorMessage', 'unknown')}")

    result = json.loads(raw)
    if result.get("error"):
        raise RuntimeError(f"Agent error: {result['error']}")

    return result.get("output", {})


class RunService:

    def __init__(self) -> None:
        self._wf_dao = WorkflowDAO()
        self._run_dao = WorkflowRunDAO()
        self._agent_dao = AgentDAO()

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger_run(self, workflow_id: str, triggered_by: str) -> dict[str, Any]:
        """
        Validate the workflow, create the run record (status=running), and return
        immediately.  The caller must schedule execute_run() as a BackgroundTask.
        """
        wf = self._get_workflow_or_404(workflow_id)
        self._assert_owner(wf, triggered_by)

        steps = wf.get("steps", [])
        if not steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow has no steps to execute",
            )
        if len(steps) > _settings.orchestrator_max_steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workflow exceeds the maximum step limit ({_settings.orchestrator_max_steps})",
            )

        return self._run_dao.create(workflow_id, triggered_by)

    def execute_run(self, workflow_id: str, run_id: str, triggered_by: str) -> None:
        """
        Execute all workflow steps and persist results to DDB.
        Designed to run inside a FastAPI BackgroundTask (separate thread).
        Any unhandled exception marks the run as failed.
        """
        try:
            wf = self._wf_dao.get(workflow_id)
            if not wf:
                return
            steps = sorted(wf.get("steps", []), key=lambda s: s.get("order", 0))
            context = self._resolve_context(wf.get("context", {}), triggered_by)
            self._execute_steps(
                workflow_id=workflow_id,
                run_id=run_id,
                steps=steps,
                context=context,
                step_outputs={},
                existing_results=[],
            )
        except Exception as exc:
            try:
                self._run_dao.update_status(
                    workflow_id, run_id, "failed",
                    finished=True, extra={"fatalError": str(exc)},
                )
            except Exception:
                pass

    def resume_run(
        self,
        workflow_id: str,
        run_id: str,
        requester_id: str,
        answer: Any,
    ) -> dict[str, Any]:
        """
        Inject the user's answer into the paused step, flip status back to running,
        and return immediately.  The caller must schedule continue_run() as a
        BackgroundTask.

        pendingStepId / pendingStepOrder are left in DDB so continue_run() can
        read them without an extra argument.
        """
        wf = self._get_workflow_or_404(workflow_id)
        self._assert_owner(wf, requester_id)

        run = self._run_dao.get(workflow_id, run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        if run["status"] != "waiting_user_input":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Run is not paused (current status: {run['status']})",
            )

        pending_step_id: str = run.get("pendingStepId", "")

        # Mark the paused step as success with the user's answer as output
        step_results: list[dict] = list(run.get("stepResults", []))
        for i, sr in enumerate(step_results):
            if sr.get("stepId") == pending_step_id:
                output_field: str = sr.get("outputField") or "answer"
                step_results[i] = {
                    **sr,
                    "status": "success",
                    "output": {output_field: answer},
                    "pendingQuestion": None,
                }
                break

        # Flip to running; pendingStepOrder stays in DDB for continue_run to read
        self._run_dao.update_status(
            workflow_id, run_id, "running", step_results=step_results
        )
        return self._run_dao.get(workflow_id, run_id)  # type: ignore[return-value]

    def continue_run(self, workflow_id: str, run_id: str, triggered_by: str) -> None:
        """
        Continue execution from after the previously paused step.
        Designed to run inside a FastAPI BackgroundTask (separate thread).
        Reads pendingStepOrder from the DDB run record written by resume_run().
        """
        try:
            wf = self._wf_dao.get(workflow_id)
            if not wf:
                return
            run = self._run_dao.get(workflow_id, run_id)
            if not run:
                return

            pending_step_order: int = run.get("pendingStepOrder", 0)
            step_results: list[dict] = list(run.get("stepResults", []))
            step_outputs: dict[str, dict] = {
                sr["stepId"]: sr.get("output", {})
                for sr in step_results
                if sr.get("status") == "success"
            }
            remaining = sorted(
                [s for s in wf["steps"] if s.get("order", 0) > pending_step_order],
                key=lambda s: s.get("order", 0),
            )
            context = self._resolve_context(wf.get("context", {}), triggered_by)
            self._execute_steps(
                workflow_id=workflow_id,
                run_id=run_id,
                steps=remaining,
                context=context,
                step_outputs=step_outputs,
                existing_results=step_results,
            )
        except Exception as exc:
            try:
                self._run_dao.update_status(
                    workflow_id, run_id, "failed",
                    finished=True, extra={"fatalError": str(exc)},
                )
            except Exception:
                pass

    def get_run(
        self, workflow_id: str, run_id: str, requester_id: str
    ) -> dict[str, Any]:
        wf = self._get_workflow_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        run = self._run_dao.get(workflow_id, run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        return run

    def list_runs(
        self, workflow_id: str, requester_id: str, limit: int = 20
    ) -> dict[str, Any]:
        wf = self._get_workflow_or_404(workflow_id)
        self._assert_owner(wf, requester_id)
        runs, _ = self._run_dao.list_by_workflow(workflow_id, limit=limit)
        return {"runs": runs, "total": len(runs)}

    # ── Core execution loop ───────────────────────────────────────────────────

    def _execute_steps(
        self,
        workflow_id: str,
        run_id: str,
        steps: list[dict],
        context: dict,
        step_outputs: dict[str, dict],
        existing_results: list[dict],
    ) -> dict[str, Any]:
        """
        Run `steps` sequentially, persisting results and terminal state to DDB.
        `existing_results` contains already-completed step results (for resume).
        Returns the final run item from DDB.
        """
        all_results: list[dict] = list(existing_results)

        for step in steps:
            t0 = time.monotonic()

            try:
                result = self._execute_single_step(step, context, step_outputs)
            except Exception as exc:
                result = {
                    "stepId": step.get("stepId", ""),
                    "type": step.get("type", ""),
                    "status": "failed",
                    "error": str(exc),
                    "input": {},
                    "output": {},
                }

            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            all_results.append(result)

            step_status: str = result["status"]

            if step_status == "failed":
                self._run_dao.update_status(
                    workflow_id, run_id, "failed",
                    step_results=all_results, finished=True,
                )
                return self._run_dao.get(workflow_id, run_id)  # type: ignore[return-value]

            if step_status == "waiting_user_input":
                self._run_dao.update_status(
                    workflow_id, run_id, "waiting_user_input",
                    step_results=all_results,
                    extra={
                        "pendingStepId": step.get("stepId", ""),
                        "pendingStepOrder": step.get("order", 0),
                    },
                )
                return self._run_dao.get(workflow_id, run_id)  # type: ignore[return-value]

            # Step succeeded — make output available to downstream steps
            step_outputs[step["stepId"]] = result.get("output", {})

        # All steps finished successfully
        self._run_dao.update_status(
            workflow_id, run_id, "success",
            step_results=all_results, finished=True,
        )
        return self._run_dao.get(workflow_id, run_id)  # type: ignore[return-value]

    def _execute_single_step(
        self, step: dict, context: dict, step_outputs: dict
    ) -> dict[str, Any]:
        step_type = step.get("type", "")
        if step_type == "AGENT":
            return self._exec_agent(step, context, step_outputs)
        if step_type == "LLM":
            return self._exec_llm(step, context, step_outputs)
        if step_type == "LOGIC":
            return self._exec_logic(step, context, step_outputs)
        raise ValueError(f"Unknown step type: {step_type!r}")

    # ── Step executors ────────────────────────────────────────────────────────

    def _exec_agent(
        self, step: dict, context: dict, step_outputs: dict
    ) -> dict[str, Any]:
        agent_id: str = step["agentId"]
        agent_version: str = step.get("agentVersion", "1.0.0")

        agent = self._agent_dao.get(agent_id, agent_version)
        if not agent:
            raise ValueError(f"Agent '{agent_id}' v{agent_version} not found")

        input_data = self._resolve_agent_input(step, agent, context, step_outputs)

        output = _invoke_agent_lambda(
            agent_id=agent_id,
            version=agent_version,
            system_prompt=agent.get("systemPrompt", ""),
            output_schema=agent.get("outputSchema", []),
            input_data=input_data,
        )

        # Best-effort callCount increment (non-critical)
        try:
            self._agent_dao.increment_call_count(agent_id, agent_version)
        except Exception:
            pass

        return {
            "stepId": step["stepId"],
            "type": "AGENT",
            "status": "success",
            "input": input_data,
            "output": output,
            "error": None,
        }

    def _exec_llm(
        self, step: dict, context: dict, step_outputs: dict
    ) -> dict[str, Any]:
        prompt = self._resolve_template(step.get("prompt", ""), context, step_outputs)
        output_schema: dict | None = step.get("outputSchema")

        kwargs: dict[str, Any] = {
            "model": _settings.claude_sonnet_model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if output_schema and isinstance(output_schema, dict) and "fieldName" in output_schema:
            hint = {output_schema["fieldName"]: output_schema.get("type", "string")}
            kwargs["system"] = (
                f"Respond with valid JSON: {json.dumps(hint, ensure_ascii=False)}"
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
            "type": "LLM",
            "status": "success",
            "input": {"prompt": prompt},
            "output": output,
            "error": None,
        }

    def _exec_logic(
        self, step: dict, context: dict, step_outputs: dict
    ) -> dict[str, Any]:
        logic_type: str = step.get("logicType", "condition")

        # ── user_input: pause and wait ────────────────────────────────────────
        if logic_type == "user_input":
            return {
                "stepId": step["stepId"],
                "type": "LOGIC",
                "status": "waiting_user_input",
                "pendingQuestion": step.get("question") or "Please provide input",
                "outputField": step.get("outputField") or "answer",
                "input": {},
                "output": {},
                "error": None,
            }

        # ── condition: evaluate and record branch (linear flow for MVP) ───────
        if logic_type == "condition":
            condition: dict = step.get("condition") or {}
            raw_expr: str = condition.get("if", "")
            resolved_expr = self._resolve_template(raw_expr, context, step_outputs)
            branch_taken = self._eval_condition(resolved_expr)
            return {
                "stepId": step["stepId"],
                "type": "LOGIC",
                "status": "success",
                "input": {"condition": raw_expr, "resolved": resolved_expr},
                "output": {
                    "result": branch_taken,
                    "branch": "then" if branch_taken else "else",
                    "nextStep": condition.get("then") if branch_taken else condition.get("else"),
                },
                "error": None,
            }

        # ── transform: pass-through placeholder for MVP ───────────────────────
        return {
            "stepId": step["stepId"],
            "type": "LOGIC",
            "status": "success",
            "input": {},
            "output": {},
            "error": None,
        }

    # ── Template resolution ───────────────────────────────────────────────────

    def _resolve_context(self, context_template: dict, triggered_by: str) -> dict:
        """
        Resolve special runtime references in workflow context values:
          {{current_user.id}}  →  the userId who triggered the run
          {{now}}              →  ISO-8601 timestamp at run start
        All other values are treated as literal strings.
        """
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

    def _resolve_template(
        self, template: str, context: dict, step_outputs: dict
    ) -> str:
        """
        Replace every {{...}} reference in `template` with its resolved value.

        Supported references:
          {{context.<key>}}              — workflow context value
          {{<stepId>.output.<field>}}    — output field of a completed step
        Unrecognised references are left as-is.
        """
        def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
            ref = m.group(1).strip()
            parts = ref.split(".")

            if parts[0] == "context" and len(parts) >= 2:
                val: Any = context.get(parts[1], "")
            elif len(parts) >= 3 and parts[1] == "output":
                val = step_outputs.get(parts[0], {}).get(parts[2], "")
            else:
                return m.group(0)  # leave unrecognised references intact

            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False)
            return str(val)

        return re.sub(r"\{\{([^}]+)\}\}", _replace, template)

    def _resolve_agent_input(
        self,
        step: dict,
        agent: dict,
        context: dict,
        step_outputs: dict,
    ) -> dict[str, Any]:
        """
        Build the concrete input dict for an AGENT step by resolving inputMapping
        and missingFieldsResolution against the available context and step outputs.
        """
        input_mapping: dict = step.get("inputMapping", {})
        missing_resolution: dict = step.get("missingFieldsResolution", {})
        result: dict[str, Any] = {}

        for field in agent.get("inputSchema", []):
            fname: str = field["fieldName"]
            default = field.get("default")

            if fname in input_mapping:
                tpl = input_mapping[fname]
                result[fname] = (
                    default
                    if tpl == "{{default}}"
                    else self._resolve_template(tpl, context, step_outputs)
                )
            elif fname in missing_resolution:
                res = missing_resolution[fname]
                result[fname] = self._resolve_template(
                    res["value"] if isinstance(res, dict) else res.value,
                    context, step_outputs,
                )
            elif default is not None:
                result[fname] = default
            # Required fields with no resolution are silently omitted here;
            # the /validate endpoint should surface them before execution.

        return result

    # ── Condition evaluator ───────────────────────────────────────────────────

    def _eval_condition(self, expr: str) -> bool:
        """
        Evaluate a simple binary comparison (>, <, >=, <=, ==, !=).
        The expression must already have {{...}} references resolved.

        Examples:  "1.2 > 0.8"   →  True
                   "done == done" →  True
        """
        for op in (">=", "<=", "!=", "==", ">", "<"):
            if op in expr:
                left_s, right_s = expr.split(op, 1)
                left_s = left_s.strip()
                right_s = right_s.strip()
                try:
                    left: Any = float(left_s)
                    right: Any = float(right_s)
                except ValueError:
                    left = left_s.strip("'\"")
                    right = right_s.strip("'\"")
                match op:
                    case ">=": return left >= right
                    case "<=": return left <= right
                    case "!=": return left != right
                    case "==": return left == right
                    case ">":  return left > right
                    case "<":  return left < right
        return False

    # ── Auth helpers ──────────────────────────────────────────────────────────

    def _get_workflow_or_404(self, workflow_id: str) -> dict[str, Any]:
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
