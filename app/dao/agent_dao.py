"""
AgentDAO

DynamoDB layout:
  PK = AGENT#<agentId>
  SK = VERSION#<version>          e.g. VERSION#1.0.0
  SK = RUN#<timestamp>#<runId>    e.g. RUN#2026-02-27T09:00:00Z#run-001
  SK = SESSION#<timestamp>#<sessionId>  (written by AgentChatSessionDAO)

GSI usage:
  GSI1_AuthorByDate      — list_by_author()     query authorId, filter entityType=AGENT
  GSI2_MarketplaceHotness — list_marketplace()  query statusVisibility="published#public"
  GSI3_AuthorByLastUsed  — future: list by most recently used
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.dao.base import BaseDAO

DEFAULT_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assign_step_ids(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every step has a non-empty stepId."""
    result = []
    for step in steps:
        s = dict(step)
        if not s.get("stepId"):
            s["stepId"] = str(uuid.uuid4())
        result.append(s)
    return result


class AgentDAO(BaseDAO):

    @staticmethod
    def _pk(agent_id: str) -> str:
        return f"AGENT#{agent_id}"

    @staticmethod
    def _version_sk(version: str) -> str:
        return f"VERSION#{version}"

    @staticmethod
    def _run_sk(run_id: str, timestamp: str) -> str:
        return f"RUN#{timestamp}#{run_id}"

    @staticmethod
    def _status_visibility(status: str, visibility: str) -> str:
        """Composite GSI-2 partition key."""
        return f"{status}#{visibility}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Agent draft.

        Required in data: name, authorId, steps (list, at least 1)
        Optional: description, inputSchema, outputSchema, visibility,
                  version, toolsRequired, level, tools
        """
        agent_id = str(uuid.uuid4())
        version = data.get("version", DEFAULT_VERSION)
        visibility = data.get("visibility", "private")
        now = _now()

        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": self._version_sk(version),
            "entityType": "AGENT",
            "agentId": agent_id,
            "version": version,
            "name": data["name"],
            "description": data.get("description", ""),
            "authorId": data["authorId"],
            "status": "draft",
            "visibility": visibility,
            "statusVisibility": self._status_visibility("draft", visibility),
            # steps: always at least 1; stepIds auto-assigned if missing
            "steps": _assign_step_ids(data.get("steps", [])),
            # top-level schemas for the agent as a whole
            "inputSchema": data.get("inputSchema", []),
            "outputSchema": data.get("outputSchema", []),
            "toolsRequired": data.get("toolsRequired", []),
            "callCount": 0,
            "lastUsedAt": None,
            "createdAt": now,
            "updatedAt": now,
            # Incremental 2 fields
            "level": data.get("level", "L1"),
            "tools": data.get("tools", []),
        }
        self._table.put_item(
            Item=item,
            ConditionExpression=self._item_not_exists_condition(),
        )
        return self._clean(item)

    def update(
        self, agent_id: str, version: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update any subset of Agent fields.
        Automatically keeps statusVisibility in sync when status or visibility changes.
        If steps are provided, stepIds are auto-assigned for any step missing one.
        """
        if "status" in fields or "visibility" in fields:
            current = self.get(agent_id, version)
            if not current:
                return None
            status = fields.get("status", current["status"])
            visibility = fields.get("visibility", current["visibility"])
            fields["statusVisibility"] = self._status_visibility(status, visibility)

        if "steps" in fields:
            fields["steps"] = _assign_step_ids(fields["steps"])

        fields["updatedAt"] = _now()
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": self._version_sk(version)},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def delete(self, agent_id: str, version: str) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(agent_id), "SK": self._version_sk(version)}
        )

    def increment_call_count(self, agent_id: str, version: str) -> None:
        """Atomic ADD — safe under concurrent executions."""
        self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": self._version_sk(version)},
            UpdateExpression="ADD callCount :one",
            ExpressionAttributeValues={":one": 1},
        )

    def update_last_used(self, agent_id: str, version: str = DEFAULT_VERSION) -> None:
        """Set lastUsedAt = now(). Called after a successful agent execution."""
        now = _now()
        self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": self._version_sk(version)},
            UpdateExpression="SET lastUsedAt = :now, updatedAt = :now",
            ExpressionAttributeValues={":now": now},
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, agent_id: str, version: str = DEFAULT_VERSION) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(agent_id), "SK": self._version_sk(version)}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_author(self, author_id: str) -> list[dict[str, Any]]:
        """GSI1_AuthorByDate: all AGENT items for this author, sorted by createdAt."""
        resp = self._table.query(
            IndexName="GSI1_AuthorByDate",
            KeyConditionExpression=Key("authorId").eq(author_id),
            FilterExpression=Attr("entityType").eq("AGENT"),
        )
        return [self._clean(item) for item in resp.get("Items", [])]

    def list_marketplace(
        self, limit: int = 20, last_key: dict | None = None
    ) -> tuple[list[dict[str, Any]], dict | None]:
        """GSI2_MarketplaceHotness: published public agents sorted by callCount desc."""
        kwargs: dict[str, Any] = {
            "IndexName": "GSI2_MarketplaceHotness",
            "KeyConditionExpression": Key("statusVisibility").eq("published#public"),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = self._table.query(**kwargs)
        return (
            [self._clean(item) for item in resp.get("Items", [])],
            resp.get("LastEvaluatedKey"),
        )

    def list_all_marketplace(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        last_key: dict | None = None
        while True:
            batch, last_key = self.list_marketplace(limit=100, last_key=last_key)
            items.extend(batch)
            if not last_key:
                break
        return items

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """Full-text keyword search across name + description via Scan."""
        kw = keyword.lower()
        items: list[dict[str, Any]] = []
        last_key: dict | None = None
        while True:
            kwargs: dict[str, Any] = {
                "FilterExpression": (
                    Attr("entityType").eq("AGENT")
                    & Attr("statusVisibility").eq("published#public")
                    & (Attr("name").contains(kw) | Attr("description").contains(kw))
                )
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self._table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return [self._clean(item) for item in items]

    # ── Runs ──────────────────────────────────────────────────────────────────
    # SK format: RUN#{timestamp}#{runId}
    # ISO timestamp sorts lexicographically = chronologically, so newest-first
    # queries work with ScanIndexForward=False.

    def create_run(self, agent_id: str, triggered_by: str) -> dict[str, Any]:
        """Create a new AGENT_RUN with status=running."""
        run_id = str(uuid.uuid4())
        now = _now()
        sk = self._run_sk(run_id, now)

        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": sk,
            "entityType": "AGENT_RUN",
            "runId": run_id,
            "agentId": agent_id,
            "triggeredBy": triggered_by,
            "status": "running",
            "stepResults": [],
            "startedAt": now,
            "finishedAt": None,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def get_run(self, agent_id: str, run_id: str, started_at: str) -> dict[str, Any] | None:
        """Get a specific run by its composite SK."""
        sk = self._run_sk(run_id, started_at)
        resp = self._table.get_item(
            Key={"PK": self._pk(agent_id), "SK": sk}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def update_run_status(
        self,
        agent_id: str,
        run_id: str,
        started_at: str,
        status: str,
        step_results: list[dict] | None = None,
        finished: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update run status and optionally replace stepResults."""
        sk = self._run_sk(run_id, started_at)
        fields: dict[str, Any] = {"status": status}
        if step_results is not None:
            fields["stepResults"] = step_results
        if finished:
            fields["finishedAt"] = _now()
        if extra:
            fields.update(extra)

        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": sk},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def get_runs(self, agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        All runs for an agent, newest first.
        SK begins_with "RUN#" + ScanIndexForward=False gives time-desc order
        because the timestamp prefix sorts lexicographically.
        """
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("RUN#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [self._clean(item) for item in resp.get("Items", [])]
