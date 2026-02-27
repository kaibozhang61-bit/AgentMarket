"""
AgentDAO

DynamoDB layout:
  PK = AGENT#<agentId>
  SK = VERSION#<version>          e.g. VERSION#1.0.0

GSI usage:
  GSI1_AuthorByDate    — list_by_author()     query authorId, filter entityType=AGENT
  GSI2_MarketplaceHotness — list_marketplace() query statusVisibility="published#public"
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.dao.base import BaseDAO

DEFAULT_VERSION = "1.0.0"


class AgentDAO(BaseDAO):

    @staticmethod
    def _pk(agent_id: str) -> str:
        return f"AGENT#{agent_id}"

    @staticmethod
    def _sk(version: str) -> str:
        return f"VERSION#{version}"

    @staticmethod
    def _status_visibility(status: str, visibility: str) -> str:
        """Composite GSI-2 partition key."""
        return f"{status}#{visibility}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Agent draft.

        Required in data: name, authorId
        Optional: description, systemPrompt, inputSchema, outputSchema,
                  visibility, version, toolsRequired, level, tools
        """
        agent_id = str(uuid.uuid4())
        version = data.get("version", DEFAULT_VERSION)
        visibility = data.get("visibility", "private")
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": self._sk(version),
            "entityType": "AGENT",
            "agentId": agent_id,
            "version": version,
            "name": data["name"],
            "description": data.get("description", ""),
            "authorId": data["authorId"],
            "status": "draft",
            "visibility": visibility,
            # Composite key kept in sync for GSI-2
            "statusVisibility": self._status_visibility("draft", visibility),
            # systemPrompt stored inline for small prompts; S3 path for large ones
            "systemPrompt": data.get("systemPrompt", ""),
            "systemPromptPath": data.get("systemPromptPath", ""),
            "inputSchema": data.get("inputSchema", []),
            "outputSchema": data.get("outputSchema", []),
            "toolsRequired": data.get("toolsRequired", []),
            "callCount": 0,
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
        """
        # Sync composite GSI-2 key if status/visibility is changing
        if "status" in fields or "visibility" in fields:
            current = self.get(agent_id, version)
            if not current:
                return None
            status = fields.get("status", current["status"])
            visibility = fields.get("visibility", current["visibility"])
            fields["statusVisibility"] = self._status_visibility(status, visibility)

        fields["updatedAt"] = datetime.now(timezone.utc).isoformat()
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": self._sk(version)},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def delete(self, agent_id: str, version: str) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(agent_id), "SK": self._sk(version)}
        )

    def increment_call_count(self, agent_id: str, version: str) -> None:
        """Atomic ADD — safe under concurrent Workflow executions."""
        self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": self._sk(version)},
            UpdateExpression="ADD callCount :one",
            ExpressionAttributeValues={":one": 1},
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, agent_id: str, version: str = DEFAULT_VERSION) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(agent_id), "SK": self._sk(version)}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_author(self, author_id: str) -> list[dict[str, Any]]:
        """
        GSI1_AuthorByDate: all AGENT items for this author, sorted by createdAt asc.
        """
        resp = self._table.query(
            IndexName="GSI1_AuthorByDate",
            KeyConditionExpression=Key("authorId").eq(author_id),
            FilterExpression=Attr("entityType").eq("AGENT"),
        )
        return [self._clean(item) for item in resp.get("Items", [])]

    def list_marketplace(
        self, limit: int = 20, last_key: dict | None = None
    ) -> tuple[list[dict[str, Any]], dict | None]:
        """
        GSI2_MarketplaceHotness: published public agents sorted by callCount desc.
        Returns (items, last_evaluated_key) for cursor-based pagination.
        """
        kwargs: dict[str, Any] = {
            "IndexName": "GSI2_MarketplaceHotness",
            "KeyConditionExpression": Key("statusVisibility").eq("published#public"),
            "ScanIndexForward": False,  # descending callCount
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
        """
        Return ALL published+public agents by exhausting GSI2 pages.
        The service layer is responsible for in-memory sorting and pagination.

        MVP note: acceptable for small datasets; replace with server-side
        cursor pagination once the catalogue grows large.
        """
        items: list[dict[str, Any]] = []
        last_key: dict | None = None
        while True:
            batch, last_key = self.list_marketplace(limit=100, last_key=last_key)
            items.extend(batch)
            if not last_key:
                break
        return items

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """
        Full-text keyword search across name + description via Scan + FilterExpression.
        Iterates all DDB pages so the caller receives every matching item.

        Important: DynamoDB's Limit on a Scan is applied *before* filtering, so
        passing Limit=20 might return 0 matches if the first 20 items don't match.
        We therefore omit Limit here and paginate through the entire table.

        MVP note: replace with OpenSearch / DDB's built-in search for production scale.
        """
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
