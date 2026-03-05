"""
StateMachineService — Build Step Functions State Machine definitions from agent steps.

Step type → State type mapping:
  type=llm              → Task State → execute_llm_lambda
  type=agent            → Task State → execute_agent_lambda (WaitForTaskToken)
  type=logic/condition  → Choice State (native, zero latency)
  type=logic/transform  → Task State → execute_transform_lambda
  type=logic/user_input → Task State → user_input_lambda (WaitForTaskToken)
"""

from __future__ import annotations

import json
from typing import Any

import boto3

from app.core.config import get_settings

_settings = get_settings()
_sfn = boto3.client("stepfunctions", region_name=_settings.aws_region)


# Lambda ARNs — configured via environment
LLM_LAMBDA_ARN = ""       # Set after deployment
AGENT_LAMBDA_ARN = ""     # Set after deployment
TRANSFORM_LAMBDA_ARN = "" # Set after deployment
USER_INPUT_LAMBDA_ARN = ""  # Set after deployment
FAILURE_LAMBDA_ARN = ""   # Set after deployment


class StateMachineService:

    def build_definition(self, agent: dict[str, Any]) -> dict[str, Any]:
        """
        Build a Step Functions state machine definition from agent steps.
        Returns the ASL (Amazon States Language) definition dict.
        """
        steps = agent.get("steps", [])
        if not steps:
            raise ValueError("Agent has no steps")

        # Sort by order
        steps = sorted(steps, key=lambda s: s.get("order", 0))

        states: dict[str, Any] = {}

        for i, step in enumerate(steps):
            step_id = step.get("stepId", f"step_{i}")
            step_type = step.get("type", "llm")
            next_state = (
                steps[i + 1].get("stepId", f"step_{i+1}")
                if i + 1 < len(steps)
                else "Succeed"
            )

            if step_type == "llm":
                states[step_id] = self._build_llm_state(step, next_state)
            elif step_type == "agent":
                states[step_id] = self._build_agent_state(step, next_state)
            elif step_type == "logic":
                logic_type = step.get("logicType", "condition")
                if logic_type == "condition":
                    states[step_id] = self._build_condition_state(step)
                elif logic_type == "transform":
                    states[step_id] = self._build_transform_state(step, next_state)
                elif logic_type == "user_input":
                    states[step_id] = self._build_user_input_state(step, next_state)

        # Terminal states
        states["Succeed"] = {"Type": "Succeed"}
        states["HandleFailure"] = {
            "Type": "Task",
            "Resource": FAILURE_LAMBDA_ARN,
            "Parameters": {
                "run_id.$": "$.run_id",
                "agent_id.$": "$.agent_id",
            },
            "Next": "Fail",
        }
        states["Fail"] = {"Type": "Fail"}

        return {
            "StartAt": steps[0].get("stepId", "step_0"),
            "States": states,
        }

    def create_state_machine(
        self,
        agent_id: str,
        version: int,
        definition: dict[str, Any],
        role_arn: str,
    ) -> str:
        """
        Create a Step Functions state machine. Returns the ARN.
        Idempotent — if a SM with this name already exists, returns its ARN.
        """
        name = f"{agent_id}-v{version}"
        try:
            resp = _sfn.create_state_machine(
                name=name,
                definition=json.dumps(definition),
                roleArn=role_arn,
                type="STANDARD",
                tags=[
                    {"key": "agentId", "value": agent_id},
                    {"key": "version", "value": str(version)},
                ],
            )
            return resp["stateMachineArn"]
        except _sfn.exceptions.StateMachineAlreadyExists:
            # Idempotent: SM was created on a previous attempt, fetch its ARN
            return self._find_state_machine_arn(name)

    def _find_state_machine_arn(self, name: str) -> str:
        """Look up an existing state machine ARN by name."""
        paginator = _sfn.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page["stateMachines"]:
                if sm["name"] == name:
                    return sm["stateMachineArn"]
        raise ValueError(f"State machine '{name}' not found")

    def delete_state_machine(self, arn: str) -> None:
        """Delete a state machine (used for cleanup)."""
        try:
            _sfn.delete_state_machine(stateMachineArn=arn)
        except Exception:
            pass  # Idempotent

    # ── State builders ────────────────────────────────────────────────────────

    @staticmethod
    def _build_llm_state(step: dict, next_state: str) -> dict[str, Any]:
        return {
            "Type": "Task",
            "Resource": LLM_LAMBDA_ARN,
            "Parameters": {
                "run_id.$": "$.run_id",
                "agent_id.$": "$.agent_id",
                "step_id": step.get("stepId", ""),
            },
            "ResultPath": "$",
            "Retry": [
                {
                    "ErrorEquals": ["Lambda.ServiceException"],
                    "MaxAttempts": 3,
                    "IntervalSeconds": 2,
                    "BackoffRate": 2,
                }
            ],
            "Catch": [
                {"ErrorEquals": ["States.ALL"], "Next": "HandleFailure"}
            ],
            "Next": next_state,
        }

    @staticmethod
    def _build_agent_state(step: dict, next_state: str) -> dict[str, Any]:
        return {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
            "Parameters": {
                "FunctionName": AGENT_LAMBDA_ARN,
                "Payload": {
                    "run_id.$": "$.run_id",
                    "agent_id.$": "$.agent_id",
                    "step_id": step.get("stepId", ""),
                    "task_token.$": "$$.Task.Token",
                },
            },
            "ResultPath": "$",
            "Catch": [
                {"ErrorEquals": ["States.ALL"], "Next": "HandleFailure"}
            ],
            "Next": next_state,
        }

    @staticmethod
    def _build_condition_state(step: dict) -> dict[str, Any]:
        condition = step.get("condition", {})
        field = condition.get("field", "")
        threshold = condition.get("threshold", 0)
        then_state = condition.get("then", "Succeed")
        else_state = condition.get("else", "Succeed")

        return {
            "Type": "Choice",
            "Choices": [
                {
                    "Variable": f"$.output.{field}",
                    "NumericGreaterThan": threshold,
                    "Next": then_state,
                }
            ],
            "Default": else_state,
        }

    @staticmethod
    def _build_transform_state(step: dict, next_state: str) -> dict[str, Any]:
        return {
            "Type": "Task",
            "Resource": TRANSFORM_LAMBDA_ARN,
            "Parameters": {
                "run_id.$": "$.run_id",
                "agent_id.$": "$.agent_id",
                "step_id": step.get("stepId", ""),
            },
            "ResultPath": "$",
            "Next": next_state,
        }

    @staticmethod
    def _build_user_input_state(step: dict, next_state: str) -> dict[str, Any]:
        return {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
            "Parameters": {
                "FunctionName": USER_INPUT_LAMBDA_ARN,
                "Payload": {
                    "run_id.$": "$.run_id",
                    "agent_id.$": "$.agent_id",
                    "step_id": step.get("stepId", ""),
                    "task_token.$": "$$.Task.Token",
                    "question": step.get("question", ""),
                },
            },
            "HeartbeatSeconds": 3600,
            "ResultPath": "$",
            "Next": next_state,
        }
