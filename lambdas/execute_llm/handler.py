"""
execute_llm_lambda — handles type=llm steps in Step Functions.

1. Read blackboard from DDB
2. Extract only declared readFromBlackboard fields
3. Call Claude with system prompt + extracted fields
4. Validate output against outputSchema
5. Write results back to blackboard
6. Return output for downstream states

Environment variables:
  DYNAMODB_TABLE_NAME, AWS_REGION, ANTHROPIC_API_KEY, CLAUDE_MODEL
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import anthropic
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "AgentMarketplace")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

_ddb = boto3.resource("dynamodb", region_name=REGION)
_table = _ddb.Table(TABLE_NAME)
_llm = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def handler(event: dict, context: Any) -> dict:
    run_id = event["run_id"]
    agent_id = event["agent_id"]
    step_id = event["step_id"]

    # Read blackboard
    blackboard = _read_blackboard(run_id, agent_id)
    step = _fetch_step(agent_id, step_id)

    if not step:
        raise ValueError(f"Step {step_id} not found in agent {agent_id}")

    # Extract declared fields
    read_from = step.get("readFromBlackboard", [])
    fields = _extract_fields(blackboard, read_from)

    # Build prompt
    system_prompt = step.get("systemPrompt", "")
    output_schema = step.get("outputSchema", [])

    if output_schema:
        schema_hint = {f["fieldName"]: f["type"] for f in output_schema}
        system_prompt += (
            f"\n\nRespond with valid JSON matching this schema: "
            f"{json.dumps(schema_hint)}"
        )

    user_message = json.dumps(fields, ensure_ascii=False, default=str)

    # Call Claude
    t0 = time.monotonic()
    response = _llm.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    raw = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    # Parse output
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"LLM returned invalid JSON: {raw[:200]}")

    # Validate against schema
    _validate_output(output, output_schema)

    # Write to blackboard
    _write_blackboard(run_id, agent_id, step_id, output, tokens_used, latency_ms)

    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "output": output,
        "status": "success",
    }


def _read_blackboard(run_id: str, agent_id: str) -> dict:
    """Read the blackboard from the run record."""
    runs = _query_run(run_id, agent_id)
    if not runs:
        return {}
    return runs[0].get("blackboard", {})


def _query_run(run_id: str, agent_id: str) -> list[dict]:
    """Find a run by runId within an agent's partition."""
    from boto3.dynamodb.conditions import Key, Attr
    resp = _table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"AGENT#{agent_id}")
            & Key("SK").begins_with("RUN#")
        ),
        FilterExpression=Attr("runId").eq(run_id),
        Limit=1,
    )
    return resp.get("Items", [])


def _fetch_step(agent_id: str, step_id: str) -> dict | None:
    """Fetch a specific step from the agent definition."""
    resp = _table.get_item(Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"})
    item = resp.get("Item")
    if not item:
        return None
    for step in item.get("steps", []):
        if step.get("stepId") == step_id:
            return step
    return None


def _extract_fields(blackboard: dict, read_from: list[str]) -> dict:
    """Extract declared fields from the blackboard."""
    fields = {}
    for path in read_from:
        val = _get_nested(blackboard, path)
        if val is not None:
            fields[path] = val
    return fields


def _get_nested(blackboard: dict, dot_path: str) -> Any:
    """Resolve a dot-path into the blackboard."""
    parts = dot_path.split(".", 1)
    key = parts[0]
    entry = blackboard.get(key)
    if not entry:
        return None
    value = entry.get("value", {}) if isinstance(entry, dict) else {}
    if len(parts) == 1:
        return value
    field = parts[1]
    return value.get(field) if isinstance(value, dict) else None


def _validate_output(output: dict, schema: list[dict]) -> None:
    """Validate output has all required fields from schema."""
    if not schema:
        return
    for field_def in schema:
        name = field_def.get("fieldName", "")
        required = field_def.get("required", True)
        if required and name not in output:
            raise ValueError(f"Missing required output field: {name}")


def _write_blackboard(
    run_id: str, agent_id: str, step_id: str,
    output: dict, tokens_used: int, latency_ms: int,
) -> None:
    """Write step output to the blackboard in the run record."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    runs = _query_run(run_id, agent_id)
    if not runs:
        return

    run = runs[0]
    blackboard = run.get("blackboard", {})
    blackboard[f"step_{step_id}_output"] = {
        "value": output,
        "writtenBy": step_id,
        "writtenAt": now,
    }

    # Update step results
    step_results = run.get("stepResults", [])
    step_results.append({
        "stepId": step_id,
        "type": "llm",
        "status": "success",
        "output": output,
        "latency_ms": latency_ms,
    })

    _table.update_item(
        Key={"PK": run["PK"], "SK": run["SK"]},
        UpdateExpression="SET blackboard = :bb, stepResults = :sr, tokensConsumed = tokensConsumed + :tc",
        ExpressionAttributeValues={
            ":bb": blackboard,
            ":sr": step_results,
            ":tc": tokens_used,
        },
    )
