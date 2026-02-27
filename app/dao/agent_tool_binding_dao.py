"""
AgentToolBindingDAO  —  Incremental 2

DynamoDB layout:
  PK = USER#<userId>
  SK = AGENT#<agentId>

Records which Connection a user has bound to an L3 Agent that requires user-provided credentials.
One record per (user, agent) pair — upsert semantics.
"""

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.dao.base import BaseDAO


class AgentToolBindingDAO(BaseDAO):

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"USER#{user_id}"

    @staticmethod
    def _sk(agent_id: str) -> str:
        return f"AGENT#{agent_id}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(
        self, user_id: str, agent_id: str, connection_id: str
    ) -> dict[str, Any]:
        """
        Bind (or rebind) a user's Connection to an Agent.
        Uses put_item unconditionally — last write wins.
        """
        now = datetime.now(timezone.utc).isoformat()
        item: dict[str, Any] = {
            "PK": self._pk(user_id),
            "SK": self._sk(agent_id),
            "entityType": "AGENT_TOOL_BINDING",
            "userId": user_id,
            "agentId": agent_id,
            "connectionId": connection_id,
            "createdAt": now,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def delete(self, user_id: str, agent_id: str) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(user_id), "SK": self._sk(agent_id)}
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, user_id: str, agent_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(user_id), "SK": self._sk(agent_id)}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """All agent bindings for a user (useful for showing 'my connected agents')."""
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(user_id))
                & Key("SK").begins_with("AGENT#")
            ),
        )
        return [self._clean(item) for item in resp.get("Items", [])]
