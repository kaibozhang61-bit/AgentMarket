"""
SearchSessionDAO — stores search/comparison sessions with metric cache.

DynamoDB layout:
  PK = SEARCH_SESSION#<sessionId>
  SK = META

Caches metric analysis results for 7 days (TTL).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.dao.base import BaseDAO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SearchSessionDAO(BaseDAO):

    @staticmethod
    def _pk(session_id: str) -> str:
        return f"SEARCH_SESSION#{session_id}"

    SK = "META"

    def create(
        self,
        user_id: str,
        agent_ids: list[str],
        user_metrics: list[str],
    ) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = _now()
        ttl = int(datetime.now(timezone.utc).timestamp()) + 7 * 24 * 3600

        item: dict[str, Any] = {
            "PK": self._pk(session_id),
            "SK": self.SK,
            "entityType": "SEARCH_SESSION",
            "sessionId": session_id,
            "userId": user_id,
            "agentIds": agent_ids,
            "userMetrics": user_metrics,
            "missingMetrics": [],
            "metricResults": {},  # {agentId: {metric: value}}
            "selectedAgent": None,
            "status": "analyzing",  # analyzing | complete
            "createdAt": now,
            "updatedAt": now,
            "ttl": ttl,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def get(self, session_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(session_id), "SK": self.SK}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def update(self, session_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        fields["updatedAt"] = _now()
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(session_id), "SK": self.SK},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])
