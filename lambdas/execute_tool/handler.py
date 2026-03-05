"""
execute_tool_lambda — handles external tool steps in Step Functions.

Receives tool config + credentials → calls external API → returns output.
Credentials fetched from Secrets Manager via connectionId.

Environment variables:
  DYNAMODB_TABLE_NAME, AWS_REGION, SECRETS_MANAGER_REGION
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.request import Request, urlopen

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "AgentMarketplace")
SM_REGION = os.environ.get("SECRETS_MANAGER_REGION", "us-east-1")

_ddb = boto3.resource("dynamodb", region_name=REGION)
_table = _ddb.Table(TABLE_NAME)
_sm = boto3.client("secretsmanager", region_name=SM_REGION)


def handler(event: dict, context: Any) -> dict:
    run_id = event["run_id"]
    agent_id = event["agent_id"]
    step_id = event["step_id"]

    step = _fetch_step(agent_id, step_id)
    if not step:
        raise ValueError(f"Step {step_id} not found")

    tool_id = step.get("toolId", "")
    tool = _fetch_tool(tool_id)
    if not tool:
        raise ValueError(f"Tool {tool_id} not found in registry")

    # Read blackboard and extract input
    blackboard = _read_blackboard(run_id, agent_id)
    read_from = step.get("readFromBlackboard", [])
    input_data = _extract_fields(blackboard, read_from)

    # Fetch credentials if needed
    connection_id = step.get("connectionId", "")
    credentials = {}
    if connection_id:
        credentials = _fetch_credentials(connection_id)

    # Execute tool
    tool_type = tool.get("category", "").lower()
    config = tool.get("config", {})

    if tool_type in ("general", "http/rest") or tool_id == "http_rest":
        output = _execute_http(config, input_data, credentials)
    else:
        # Generic HTTP-based execution for all tool types
        output = _execute_http(config, input_data, credentials)

    # Write to blackboard
    _write_blackboard(run_id, agent_id, step_id, output)

    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "output": output,
        "status": "success",
    }


def _execute_http(
    config: dict, input_data: dict, credentials: dict
) -> dict:
    """Generic HTTP execution for tool integrations."""
    url = config.get("url", "")
    method = config.get("method", "POST").upper()
    headers = dict(config.get("headers", {}))

    # Inject credentials into headers
    if credentials.get("api_key"):
        headers["Authorization"] = f"Bearer {credentials['api_key']}"
    if credentials.get("token"):
        headers["Authorization"] = f"Bearer {credentials['token']}"

    headers.setdefault("Content-Type", "application/json")

    body = json.dumps(input_data).encode() if method in ("POST", "PUT", "PATCH") else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw_response": raw}
    except Exception as e:
        return {"error": str(e)}


def _fetch_step(agent_id: str, step_id: str) -> dict | None:
    resp = _table.get_item(Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"})
    item = resp.get("Item")
    if not item:
        return None
    for step in item.get("steps", []):
        if step.get("stepId") == step_id:
            return step
    return None


def _fetch_tool(tool_id: str) -> dict | None:
    resp = _table.get_item(Key={"PK": f"TOOL#{tool_id}", "SK": "META"})
    return resp.get("Item")


def _fetch_credentials(connection_id: str) -> dict:
    """Fetch credentials from Secrets Manager."""
    try:
        resp = _sm.get_secret_value(SecretId=connection_id)
        return json.loads(resp["SecretString"])
    except Exception:
        return {}


def _read_blackboard(run_id: str, agent_id: str) -> dict:
    from boto3.dynamodb.conditions import Key, Attr
    resp = _table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"AGENT#{agent_id}") & Key("SK").begins_with("RUN#")
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
        entry = blackboard.get(parts[0])
        if not entry:
            continue
        value = entry.get("value", {}) if isinstance(entry, dict) else {}
        if len(parts) == 1:
            fields[parts[0]] = value
        elif isinstance(value, dict):
            fields[parts[1]] = value.get(parts[1])
    return fields


def _write_blackboard(run_id: str, agent_id: str, step_id: str, output: dict) -> None:
    import datetime
    from boto3.dynamodb.conditions import Key, Attr
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    resp = _table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"AGENT#{agent_id}") & Key("SK").begins_with("RUN#")
        ),
        FilterExpression=Attr("runId").eq(run_id),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return
    run = items[0]
    bb = run.get("blackboard", {})
    bb[f"step_{step_id}_output"] = {"value": output, "writtenBy": step_id, "writtenAt": now}
    sr = run.get("stepResults", [])
    sr.append({"stepId": step_id, "type": "tool", "status": "success", "output": output})
    _table.update_item(
        Key={"PK": run["PK"], "SK": run["SK"]},
        UpdateExpression="SET blackboard = :bb, stepResults = :sr",
        ExpressionAttributeValues={":bb": bb, ":sr": sr},
    )
