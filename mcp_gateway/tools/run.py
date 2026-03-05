"""
run_agent MCP tool — execute a published agent via Step Functions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from mcp_gateway.config import AWS_REGION, DYNAMODB_TABLE_NAME

_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
_table = _ddb.Table(DYNAMODB_TABLE_NAME)
_sfn = boto3.client("stepfunctions", region_name=AWS_REGION)


def run_agent(
    agent_id: str,
    input_data: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """
    Execute a published agent.

    1. Fetch LATEST version from DDB
    2. Validate status=active and state_machine_arn exists
    3. Create run record with agent_input on blackboard
    4. StartExecution on the agent's State Machine
    5. Return run_id for polling

    Token freeze is handled by the execution pipeline (Step 27).
    """
    # Fetch agent LATEST
    resp = _table.get_item(Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"})
    item = resp.get("Item")
    if not item:
        return {"error": f"Agent '{agent_id}' not found"}

    status = item.get("status", "")
    arn = item.get("stateMachineArn", "")

    if status != "published":
        return {"error": f"Agent '{agent_id}' is not published (status={status})"}

    # If no state machine ARN yet (pre-Step 9), fall back to in-process
    if not arn:
        return {
            "error": "Agent does not have a State Machine yet. "
                     "Use POST /agents/{agentId}/run for in-process execution."
        }

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Create run record
    run_item = {
        "PK": f"AGENT#{agent_id}",
        "SK": f"RUN#{now}#{run_id}",
        "entityType": "AGENT_RUN",
        "runId": run_id,
        "agentId": agent_id,
        "triggeredBy": user_id,
        "status": "running",
        "blackboard": {
            "agent_input": {
                "value": input_data,
                "writtenBy": "agent_input",
                "writtenAt": now,
            }
        },
        "stepResults": [],
        "tokensConsumed": 0,
        "startedAt": now,
        "finishedAt": None,
    }
    _table.put_item(Item=run_item)

    # Start Step Functions execution
    try:
        _sfn.start_execution(
            stateMachineArn=arn,
            name=run_id,
            input=json.dumps({
                "run_id": run_id,
                "agent_id": agent_id,
                "output": {},
            }),
        )
    except _sfn.exceptions.ExecutionAlreadyExists:
        return {"error": f"Run '{run_id}' already exists"}
    except Exception as e:
        # Update run status to failed
        _table.update_item(
            Key={"PK": f"AGENT#{agent_id}", "SK": f"RUN#{now}#{run_id}"},
            UpdateExpression="SET #s = :s, finishedAt = :f",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "failed", ":f": now},
        )
        return {"error": f"Failed to start execution: {str(e)}"}

    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "status": "running",
    }
