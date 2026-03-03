"""
AgentChatSessionDAO

DynamoDB layout (shares the AgentMarketplace single table):
  PK = AGENT#<agentId>
  SK = SESSION#<timestamp>#<sessionId>

Co-located with the parent Agent so all agent-related data lives under
the same partition key.  The ISO-8601 timestamp prefix in the SK means
DDB range queries return sessions in chronological order automatically.

Stages: clarifying → confirming → planning → editing → saved
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.dao.base import BaseDAO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentChatSessionDAO(BaseDAO):

    @staticmethod
    def _pk(agent_id: str) -> str:
        return f"AGENT#{agent_id}"

    @staticmethod
    def _sk(timestamp: str, session_id: str) -> str:
        return f"SESSION#{timestamp}#{session_id}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, agent_id: str, user_id: str) -> dict[str, Any]:
        """
        Create a new chat session for an agent being built.
        Initial stage is 'clarifying' with an empty history.
        """
        session_id = str(uuid.uuid4())
        now = _now()
        sk = self._sk(now, session_id)

        item: dict[str, Any] = {
            "PK": self._pk(agent_id),
            "SK": sk,
            "entityType": "AGENT_CHAT_SESSION",
            "sessionId": session_id,
            "agentId": agent_id,
            "userId": user_id,
            "stage": "clarifying",
            "history": [],
            "createdAt": now,
            "updatedAt": now,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def update(
        self,
        agent_id: str,
        session_id: str,
        created_at: str,
        *,
        stage: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Update session stage and/or history.
        At least one of stage or history must be provided.
        """
        fields: dict[str, Any] = {"updatedAt": _now()}
        if stage is not None:
            fields["stage"] = stage
        if history is not None:
            fields["history"] = history

        sk = self._sk(created_at, session_id)
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(agent_id), "SK": sk},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(
        self, agent_id: str, session_id: str, created_at: str
    ) -> dict[str, Any] | None:
        """Get a specific session by its composite SK."""
        sk = self._sk(created_at, session_id)
        resp = self._table.get_item(
            Key={"PK": self._pk(agent_id), "SK": sk}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def get_latest(self, agent_id: str) -> dict[str, Any] | None:
        """
        Return the most recent session for an agent.

        PK = AGENT#{agentId}, SK begins_with "SESSION#"
        ScanIndexForward=False → newest first, Limit=1
        """
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("SESSION#")
            ),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get("Items", [])
        return self._clean(items[0]) if items else None

    def find_by_session_id(self, agent_id: str, session_id: str) -> dict[str, Any] | None:
        """
        Look up a session when you have the sessionId but not the createdAt
        timestamp needed for the full SK.  Uses a query with a filter since
        sessionId is not part of the key structure alone.

        For the expected usage pattern (one or two sessions per agent draft)
        this is efficient — the query scans only SESSION# items under the
        agent's partition.
        """
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("SESSION#")
            ),
            ScanIndexForward=False,
        )
        for item in resp.get("Items", []):
            if item.get("sessionId") == session_id:
                return self._clean(item)
        return None

    def list_by_agent(
        self, agent_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """All sessions for an agent, newest first."""
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(agent_id))
                & Key("SK").begins_with("SESSION#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [self._clean(item) for item in resp.get("Items", [])]

    # ── Convenience ───────────────────────────────────────────────────────────

    def get_or_create(
        self,
        session_id: str | None,
        agent_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        If session_id is provided, fetch the existing session.
        Otherwise create a new one.

        This is the main entry point used by the chat endpoint.
        """
        if session_id:
            session = self.find_by_session_id(agent_id, session_id)
            if session:
                return session
            # session_id was given but not found — create fresh
        return self.create(agent_id, user_id)
