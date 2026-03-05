"""
Recovery Job Lambda — scans for agents stuck in status=pending and completes publish.

Runs every minute via EventBridge schedule.
Handles the crash recovery case where DDB was written (status=pending)
but the State Machine creation or DDB update to active failed.

Environment variables:
  DYNAMODB_TABLE_NAME
  AWS_REGION
  SFN_ROLE_ARN — IAM role for Step Functions state machines
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "AgentMarketplace")
SFN_ROLE_ARN = os.environ.get("SFN_ROLE_ARN", "")

_ddb = boto3.resource("dynamodb", region_name=REGION)
_table = _ddb.Table(TABLE_NAME)
_sfn = boto3.client("stepfunctions", region_name=REGION)


def handler(event: dict, context: Any) -> dict:
    """Scan for pending agents and attempt to complete their publish."""
    pending = _scan_pending()
    logger.info(f"Found {len(pending)} pending agents")

    recovered = 0
    for agent in pending:
        try:
            _recover(agent)
            recovered += 1
        except Exception:
            logger.exception(f"Failed to recover agent {agent.get('agentId')}")

    return {"scanned": len(pending), "recovered": recovered}


def _scan_pending() -> list[dict[str, Any]]:
    """Find all AGENT items with status=pending."""
    resp = _table.scan(
        FilterExpression=(
            Attr("entityType").eq("AGENT")
            & Attr("status").eq("pending")
        ),
    )
    return resp.get("Items", [])


def _recover(agent: dict[str, Any]) -> None:
    """Attempt to complete a pending publish."""
    agent_id = agent["agentId"]
    version = agent.get("version", "LATEST")

    # Check if State Machine already exists
    sm_name = f"{agent_id}-v{version}"
    arn = _find_state_machine(sm_name)

    if not arn:
        # Build and create the State Machine
        from app.services.state_machine_service import StateMachineService
        sm_svc = StateMachineService()
        definition = sm_svc.build_definition(agent)
        arn = sm_svc.create_state_machine(agent_id, version, definition, SFN_ROLE_ARN)

    # Update DDB to active
    _table.update_item(
        Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"},
        UpdateExpression="SET #s = :s, stateMachineArn = :arn, statusVisibility = :sv",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "published",
            ":arn": arn,
            ":sv": "published#public",
        },
    )
    logger.info(f"Recovered agent {agent_id} → active with ARN {arn}")


def _find_state_machine(name: str) -> str | None:
    """Check if a state machine with this name already exists."""
    try:
        paginator = _sfn.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page["stateMachines"]:
                if sm["name"] == name:
                    return sm["stateMachineArn"]
    except Exception:
        pass
    return None
