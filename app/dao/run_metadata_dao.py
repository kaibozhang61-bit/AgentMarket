"""
RunMetadataDAO — stores public blackboard snapshots after each execution.

DynamoDB layout:
  PK = AGENT#<agentId>
  SK = RUNMETA#<timestamp>#<runId>

Only public blackboard fields are recorded. Private fields are never written.
Used by metrics analysis (Step 5) and weekly builder reports (Step 21).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.dao.base import BaseDAO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunMetadataDAO(BaseDAO):

    @staticmethod
    def _pk(agent_id: str) -> str:
        return f"AGENT#{agent_id}"

    @staticmethod
    def _sk(timestamp: str, run_id: str) -> str:
        return f"RUNMETA#{timestamp}#{run_id}"

    def create(
        self,
        agent_id: str,
        run_id: str,
        user_id: str,
        status: str,
        duration_ms: int,
        tokens_consumed: int,
        blackboard_snapshot: dict[str, Any],
        execution_arn: str = "",
    ) -> dict[str, Any]:
        """Write a public blackboard snapshot after execution completes."""
        now = _now()
        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": self._sk(now, run_id),
            "entityType": "RUN_METADATA",
            "runId": run_id,
            "agentId": agent_id,
            "userId": user_id,
            "status": status,
            "durationMs": duration_ms,
            "tokensConsumed": tokens_consumed,
            "blackboardSnapshot": blackboard_snapshot,
            "executionArn": execution_arn,
            "startedAt": now,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def get_by_agent(
        self, agent_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch recent run metadata for an agent, newest first."""
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("RUNMETA#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [self._clean(item) for item in resp.get("Items", [])]

    @staticmethod
    def extract_public_snapshot(
        blackboard: dict[str, Any],
        agent_steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Extract only public fields from the blackboard.
        Walks each step's outputSchema and includes fields with visibility=public.
        """
        snapshot: dict[str, Any] = {}

        # Include agent_input (always public)
        agent_input = blackboard.get("agent_input", {})
        if isinstance(agent_input, dict):
            snapshot.update(agent_input.get("value", {}))

        # Walk steps and extract public output fields
        for step in agent_steps:
            step_id = step.get("stepId", "")
            bb_key = f"step_{step_id}_output"
            entry = blackboard.get(bb_key, {})
            if not isinstance(entry, dict):
                continue
            value = entry.get("value", {})
            if not isinstance(value, dict):
                continue

            output_schema = step.get("outputSchema", [])
            for field_def in output_schema:
                if field_def.get("visibility", "public") == "public":
                    field_name = field_def.get("fieldName", "")
                    if field_name in value:
                        snapshot[field_name] = value[field_name]

        return snapshot
