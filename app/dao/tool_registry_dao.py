"""
ToolRegistryDAO — stores tool definitions for external integrations.

DynamoDB layout:
  PK = TOOL#<toolId>
  SK = META

Each tool has: name, category, auth_type, inputSchema, outputSchema, config.
20 built-in tools seeded by scripts/seed_tool_registry.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.dao.base import BaseDAO


class ToolRegistryDAO(BaseDAO):

    @staticmethod
    def _pk(tool_id: str) -> str:
        return f"TOOL#{tool_id}"

    SK = "META"

    def create(self, tool_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        item: dict[str, Any] = {
            "PK": self._pk(tool_id),
            "SK": self.SK,
            "entityType": "TOOL",
            "toolId": tool_id,
            "name": data["name"],
            "category": data.get("category", "General"),
            "description": data.get("description", ""),
            "authType": data.get("authType", "none"),  # none | api_key | oauth2 | credentials
            "inputSchema": data.get("inputSchema", []),
            "outputSchema": data.get("outputSchema", []),
            "config": data.get("config", {}),
            "createdAt": now,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def get(self, tool_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(Key={"PK": self._pk(tool_id), "SK": self.SK})
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_all(self) -> list[dict[str, Any]]:
        resp = self._table.scan(
            FilterExpression=Attr("entityType").eq("TOOL"),
        )
        return [self._clean(item) for item in resp.get("Items", [])]
