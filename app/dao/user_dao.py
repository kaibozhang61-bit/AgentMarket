"""
UserDAO

DynamoDB layout:
  PK = USER#<userId>
  SK = PROFILE
"""

from datetime import datetime, timezone
from typing import Any

from app.dao.base import BaseDAO


class UserDAO(BaseDAO):

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"USER#{user_id}"

    SK = "PROFILE"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create user profile. userId comes from Cognito sub.
        Raises ConditionalCheckFailedException if user already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "PK": self._pk(user_id),
            "SK": self.SK,
            "entityType": "USER",
            "userId": user_id,
            "email": data["email"],
            "username": data["username"],
            "createdAt": now,
            "updatedAt": now,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression=self._item_not_exists_condition(),
        )
        return self._clean(item)

    def update(self, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update mutable profile fields (e.g. username)."""
        fields["updatedAt"] = datetime.now(timezone.utc).isoformat()
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(user_id), "SK": self.SK},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, user_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(user_id), "SK": self.SK}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None
