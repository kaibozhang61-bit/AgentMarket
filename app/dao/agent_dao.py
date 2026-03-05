"""
AgentDAO

DynamoDB layout:
  PK = AGENT#<agentId>
  SK = LATEST                             ← current published (or only draft) version
  SK = DRAFT                              ← work-in-progress edits to a published agent
  SK = VERSION#<timestamp>                ← archived snapshot (future version history)
  SK = RUN#<timestamp>#<runId>            ← execution records
  SK = SESSION#<timestamp>#<sessionId>    ← chat sessions (written by AgentChatSessionDAO)

Referencing agents:
  Other agents reference by agentId alone. At runtime, the DAO fetches
  SK=LATEST — always the current live version. No version number in the
  reference means no fan-out updates when an agent is republished.

GSI usage:
  GSI1_AuthorByDate       — list_by_author()    query authorId, filter entityType=AGENT
  GSI2_MarketplaceHotness — list_marketplace()   query statusVisibility="published#public"
  GSI3_AuthorByLastUsed   — future: list by most recently used
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.dao.base import BaseDAO

SK_LATEST = "LATEST"
SK_DRAFT = "DRAFT"


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
    def _run_sk(run_id: str, timestamp: str) -> str:
        return f"RUN#{timestamp}#{run_id}"

    @staticmethod
    def _version_sk(timestamp: str) -> str:
        return f"VERSION#{timestamp}"

    @staticmethod
    def _status_visibility(status: str, visibility: str) -> str:
        return f"{status}#{visibility}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Agent with SK=LATEST and status=draft.
        """
        agent_id = str(uuid.uuid4())
        visibility = data.get("visibility", "private")
        now = _now()

        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": SK_LATEST,
            "entityType": "AGENT",
            "agentId": agent_id,
            "version": SK_LATEST,
            "name": data["name"],
            "description": data.get("description", ""),
            "authorId": data["authorId"],
            "status": "draft",
            "visibility": visibility,
            "statusVisibility": self._status_visibility("draft", visibility),
            "steps": _assign_step_ids(data.get("steps", [])),
            "inputSchema": data.get("inputSchema", []),
            "outputSchema": data.get("outputSchema", []),
            "toolsRequired": data.get("toolsRequired", []),
            "context": data.get("context", {}),
            "callCount": 0,
            "lastUsedAt": None,
            "createdAt": now,
            "updatedAt": now,
            "level": data.get("level", "L1"),
            "tools": data.get("tools", []),
        }
        self._table.put_item(
            Item=item,
            ConditionExpression=self._item_not_exists_condition(),
        )
        return self._clean(item)

    def update(
        self, agent_id: str, sk: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update fields on an agent item (LATEST or DRAFT).
        Keeps statusVisibility in sync. Auto-assigns stepIds.
        """
        if "status" in fields or "visibility" in fields:
            current = self._get_by_sk(agent_id, sk)
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
            Key={"PK": self._pk(agent_id), "SK": sk},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def save_draft(self, agent_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """
        Save a DRAFT version of a published agent.
        Creates the DRAFT item if it doesn't exist, or updates it.
        The LATEST item stays untouched (live for other agents).
        """
        existing_draft = self._get_by_sk(agent_id, SK_DRAFT)
        if existing_draft:
            return self.update(agent_id, SK_DRAFT, fields)  # type: ignore[return-value]

        # Copy LATEST to DRAFT, then apply fields
        latest = self.get(agent_id)
        if not latest:
            raise ValueError(f"Agent '{agent_id}' not found")

        item = {**latest}
        item["SK"] = SK_DRAFT
        item["PK"] = self._pk(agent_id)
        item["version"] = SK_DRAFT
        item["status"] = "draft"
        item["statusVisibility"] = self._status_visibility("draft", item.get("visibility", "private"))
        item.update(fields)
        item["updatedAt"] = _now()
        if "steps" in item:
            item["steps"] = _assign_step_ids(item["steps"])

        self._table.put_item(Item=item)
        return self._clean(item)

    def publish_draft(self, agent_id: str, extra_fields: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        Promote DRAFT → LATEST.
        1. Archive current LATEST as VERSION#<timestamp>
        2. Copy DRAFT content into LATEST with status=published
        3. Delete the DRAFT item
        """
        latest = self.get(agent_id)
        draft = self._get_by_sk(agent_id, SK_DRAFT)

        if not latest and not draft:
            return None

        # If there's a published LATEST, archive it
        if latest and latest.get("status") == "published":
            archive = {**latest}
            archive_ts = latest.get("updatedAt", _now())
            archive["SK"] = self._version_sk(archive_ts)
            archive["version"] = archive_ts
            archive["statusVisibility"] = self._status_visibility("archived", archive.get("visibility", "private"))
            self._table.put_item(Item=archive)

        # Source is DRAFT if it exists, otherwise LATEST (first publish)
        source = draft if draft else latest
        if not source:
            return None

        now = _now()
        source["SK"] = SK_LATEST
        source["PK"] = self._pk(agent_id)
        source["version"] = SK_LATEST
        source["status"] = "published"
        source["visibility"] = "public"
        source["statusVisibility"] = self._status_visibility("published", "public")
        source["updatedAt"] = now
        if "steps" in source:
            source["steps"] = _assign_step_ids(source["steps"])

        # Apply extra fields (e.g. stateMachineArn from crash-safe publish)
        if extra_fields:
            source.update(extra_fields)

        self._table.put_item(Item=source)

        # Clean up DRAFT item
        if draft:
            self._table.delete_item(
                Key={"PK": self._pk(agent_id), "SK": SK_DRAFT}
            )

        return self._clean(source)

    def delete(self, agent_id: str, sk: str = SK_LATEST) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(agent_id), "SK": sk}
        )

    def increment_call_count(self, agent_id: str, sk: str = SK_LATEST) -> None:
        self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": sk},
            UpdateExpression="ADD callCount :one",
            ExpressionAttributeValues={":one": 1},
        )

    def update_last_used(self, agent_id: str, sk: str = SK_LATEST) -> None:
        now = _now()
        self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": sk},
            UpdateExpression="SET lastUsedAt = :now, updatedAt = :now",
            ExpressionAttributeValues={":now": now},
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, agent_id: str) -> dict[str, Any] | None:
        """Get the LATEST version of an agent. This is what other agents reference."""
        return self._get_by_sk(agent_id, SK_LATEST)

    def get_draft(self, agent_id: str) -> dict[str, Any] | None:
        """Get the DRAFT version if it exists."""
        return self._get_by_sk(agent_id, SK_DRAFT)

    def get_latest_or_draft(self, agent_id: str) -> dict[str, Any] | None:
        """Get DRAFT if it exists, otherwise LATEST. For the author's edit view."""
        draft = self.get_draft(agent_id)
        return draft if draft else self.get(agent_id)

    def _get_by_sk(self, agent_id: str, sk: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(agent_id), "SK": sk}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_author(self, author_id: str) -> list[dict[str, Any]]:
        """GSI1_AuthorByDate: all AGENT items for this author, sorted by createdAt."""
        resp = self._table.query(
            IndexName="GSI1_AuthorByDate",
            KeyConditionExpression=Key("authorId").eq(author_id),
            FilterExpression=(
                Attr("entityType").eq("AGENT")
                & Attr("SK").eq(SK_LATEST)
            ),
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

    def create_run(self, agent_id: str, triggered_by: str) -> dict[str, Any]:
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
            "blackboard": {},
            "startedAt": now,
            "finishedAt": None,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def get_run(self, agent_id: str, run_id: str, started_at: str) -> dict[str, Any] | None:
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
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("RUN#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [self._clean(item) for item in resp.get("Items", [])]

    def get_runs_by_user(
        self, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """GSI4_RunsByUser: all runs triggered by a user, newest first."""
        resp = self._table.query(
            IndexName="GSI4_RunsByUser",
            KeyConditionExpression=Key("triggeredBy").eq(user_id),
            FilterExpression=Attr("entityType").eq("AGENT_RUN"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [self._clean(item) for item in resp.get("Items", [])]
