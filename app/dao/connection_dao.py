"""
ConnectionDAO  —  Incremental 2

DynamoDB layout:
  PK = USER#<userId>
  SK = CONNECTION#<connectionId>

Querying all connections for a user is a single Query on PK with SK begins_with "CONNECTION#".
Actual credentials are stored in AWS Secrets Manager; only secretArn is stored here.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.dao.base import BaseDAO


class ConnectionDAO(BaseDAO):

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"USER#{user_id}"

    @staticmethod
    def _sk(connection_id: str) -> str:
        return f"CONNECTION#{connection_id}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Connection record after credentials have been stored in Secrets Manager.

        Required in data: name, type, secretArn
        Optional: allowedOperations
        type: POSTGRES | MYSQL | MONGODB | HTTP
        """
        connection_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": self._pk(user_id),
            "SK": self._sk(connection_id),
            "entityType": "CONNECTION",
            "connectionId": connection_id,
            "userId": user_id,
            "name": data["name"],
            "type": data["type"],                           # POSTGRES | MYSQL | MONGODB | HTTP
            "status": "untested",                           # untested | active | failed
            "secretArn": data["secretArn"],                 # Secrets Manager ARN — no plaintext here
            "allowedOperations": data.get("allowedOperations", ["SELECT"]),
            "createdAt": now,
            "lastTestedAt": None,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression=self._item_not_exists_condition(),
        )
        return self._clean(item)

    def update_status(
        self,
        user_id: str,
        connection_id: str,
        status: str,
    ) -> dict[str, Any]:
        """Update status + lastTestedAt after a connection test."""
        fields: dict[str, Any] = {
            "status": status,
            "lastTestedAt": datetime.now(timezone.utc).isoformat(),
        }
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(user_id), "SK": self._sk(connection_id)},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def delete(self, user_id: str, connection_id: str) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(user_id), "SK": self._sk(connection_id)}
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, user_id: str, connection_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(user_id), "SK": self._sk(connection_id)}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """All connections owned by a user, sorted by createdAt (SK insertion order)."""
        resp = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk(user_id))
                & Key("SK").begins_with("CONNECTION#")
            ),
        )
        return [self._clean(item) for item in resp.get("Items", [])]
