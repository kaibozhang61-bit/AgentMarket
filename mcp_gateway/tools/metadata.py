"""
fetch_run_metadata MCP tool — retrieve run history for metrics analysis.
"""

from __future__ import annotations

from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from mcp_gateway.config import AWS_REGION, DYNAMODB_TABLE_NAME

_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
_table = _ddb.Table(DYNAMODB_TABLE_NAME)


def fetch_run_metadata(
    agent_ids: list[str],
    last_n: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """
    Fetch the last N run_metadata records for each agent.

    Returns a dict keyed by agent_id, each containing a list of
    blackboard_snapshot dicts (public fields only).
    """
    result: dict[str, list[dict[str, Any]]] = {}

    for agent_id in agent_ids:
        resp = _table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"AGENT#{agent_id}")
                & Key("SK").begins_with("RUNMETA#")
            ),
            ScanIndexForward=False,
            Limit=last_n,
        )
        items = resp.get("Items", [])
        runs = []
        for item in items:
            runs.append({
                "run_id": item.get("runId", ""),
                "status": item.get("status", ""),
                "duration_ms": int(item.get("durationMs", 0)),
                "tokens_consumed": int(item.get("tokensConsumed", 0)),
                "blackboard_snapshot": item.get("blackboardSnapshot", {}),
                "started_at": item.get("startedAt", ""),
            })
        result[agent_id] = runs

    return result
