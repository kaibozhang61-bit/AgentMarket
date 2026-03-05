"""
execute_agent_lambda — handles type=agent steps (nested agent execution).

Triggers inner agent's StartExecution and returns immediately.
Outer State Machine suspends via WaitForTaskToken.
Inner agent's last step calls SendTaskSuccess when done.

Environment variables:
  DYNAMODB_TABLE_NAME, AWS_REGION
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "AgentMarketplace")

_ddb = boto3.resource("dynamodb", region_name=REGION)
_table = _ddb.Table(TABLE_NAME)
_sfn = boto3.client("stepfunctions", region_name=REGION)


def handler(event: dict, context: Any) -> None:
    """
    Trigger inner agent execution. Returns immediately.
    Outer state machine waits via WaitForTaskToken.
    """
    task_token = event["task_token"]
    run_id = event["run_id"]
    agent_id = event["agent_id"]
    step_id = event["step_id"]

    # Fetch step definition to get inner agentId
    step = _fetch_step(agent_id, step_id)
    if not step:
        _sfn.send_task_failure(
            taskToken=task_token,
            error="StepNotFound",
            cause=f"Step {step_id} not found in agent {agent_id}",
        )
        return

    inner_agent_id = step.get("agentId", "")
    if not inner_agent_id:
        _sfn.send_task_failure(
            taskToken=task_token,
            error="MissingAgentId",
            cause="Agent step has no agentId",
        )
        return

    # Fetch inner agent's state machine ARN
    resp = _table.get_item(Key={"PK": f"AGENT#{inner_agent_id}", "SK": "LATEST"})
    inner_agent = resp.get("Item")
    if not inner_agent or inner_agent.get("status") != "published":
        _sfn.send_task_failure(
            taskToken=task_token,
            error="AgentNotReady",
            cause=f"Inner agent {inner_agent_id} is not published",
        )
        return

    inner_arn = inner_agent.get("stateMachineArn", "")
    if not inner_arn:
        _sfn.send_task_failure(
            taskToken=task_token,
            error="NoStateMachine",
            cause=f"Inner agent {inner_agent_id} has no state machine",
        )
        return

    # Read blackboard and extract fields for inner agent
    blackboard = _read_blackboard(run_id, agent_id)
    read_from = step.get("readFromBlackboard", [])
    input_data = _extract_fields(blackboard, read_from)

    # Create inner run record
    inner_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    inner_run = {
        "PK": f"AGENT#{inner_agent_id}",
        "SK": f"RUN#{now}#{inner_run_id}",
        "entityType": "AGENT_RUN",
        "runId": inner_run_id,
        "agentId": inner_agent_id,
        "triggeredBy": _get_run_user(run_id, agent_id),
        "status": "running",
        "blackboard": {
            "agent_input": {"value": input_data, "writtenBy": "agent_input", "writtenAt": now}
        },
        "stepResults": [],
        "tokensConsumed": 0,
        "startedAt": now,
        "finishedAt": None,
        # Outer context for callback
        "outerTaskToken": task_token,
        "outerRunId": run_id,
        "outerAgentId": agent_id,
        "outerStepId": step_id,
    }
    _table.put_item(Item=inner_run)

    # Start inner execution
    try:
        _sfn.start_execution(
            stateMachineArn=inner_arn,
            name=inner_run_id,
            input=json.dumps({
                "run_id": inner_run_id,
                "agent_id": inner_agent_id,
                "output": {},
            }),
        )
        logger.info(f"Started inner execution {inner_run_id} for agent {inner_agent_id}")
    except Exception as e:
        _sfn.send_task_failure(
            taskToken=task_token,
            error="StartExecutionFailed",
            cause=str(e),
        )

    # Lambda returns immediately. Outer SM waits on WaitForTaskToken.


def _fetch_step(agent_id: str, step_id: str) -> dict | None:
    resp = _table.get_item(Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"})
    item = resp.get("Item")
    if not item:
        return None
    for step in item.get("steps", []):
        if step.get("stepId") == step_id:
            return step
    return None


def _read_blackboard(run_id: str, agent_id: str) -> dict:
    from boto3.dynamodb.conditions import Key, Attr
    resp = _table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"AGENT#{agent_id}")
            & Key("SK").begins_with("RUN#")
        ),
        FilterExpression=Attr("runId").eq(run_id),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0].get("blackboard", {}) if items else {}


def _extract_fields(blackboard: dict, read_from: list[str]) -> dict:
    fields = {}
    for path in read_from:
        parts = path.split(".", 1)
        key = parts[0]
        entry = blackboard.get(key)
        if not entry:
            continue
        value = entry.get("value", {}) if isinstance(entry, dict) else {}
        if len(parts) == 1:
            fields[key] = value
        elif isinstance(value, dict):
            fields[parts[1]] = value.get(parts[1])
    return fields


def _get_run_user(run_id: str, agent_id: str) -> str:
    from boto3.dynamodb.conditions import Key, Attr
    resp = _table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"AGENT#{agent_id}")
            & Key("SK").begins_with("RUN#")
        ),
        FilterExpression=Attr("runId").eq(run_id),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0].get("triggeredBy", "") if items else ""
