"""
WorkflowDAO

DynamoDB layout:
  PK = WORKFLOW#<workflowId>
  SK = METADATA

GSI usage:
  GSI1_AuthorByDate — list_by_author()  query authorId, filter entityType=WORKFLOW
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.dao.base import BaseDAO


class WorkflowDAO(BaseDAO):

    @staticmethod
    def _pk(workflow_id: str) -> str:
        return f"WORKFLOW#{workflow_id}"

    SK = "METADATA"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new Workflow draft.

        Required in data: name, authorId
        Optional: description, context, steps
        """
        workflow_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": self._pk(workflow_id),
            "SK": self.SK,
            "entityType": "WORKFLOW",
            "workflowId": workflow_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "authorId": data["authorId"],
            # context: map of global variables available to all steps
            # e.g. {"userId": "{{current_user.id}}", "custom_var": "fixed"}
            "context": data.get("context", {}),
            # steps: ordered list of WorkflowStep dicts (AGENT / LLM / LOGIC)
            "steps": data.get("steps", []),
            "status": "draft",
            "createdAt": now,
            "updatedAt": now,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression=self._item_not_exists_condition(),
        )
        return self._clean(item)

    def update(self, workflow_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Update any subset of Workflow fields (name, description, context, steps, status)."""
        fields["updatedAt"] = datetime.now(timezone.utc).isoformat()
        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(workflow_id), "SK": self.SK},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=self._item_exists_condition(),
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def delete(self, workflow_id: str) -> None:
        self._table.delete_item(
            Key={"PK": self._pk(workflow_id), "SK": self.SK}
        )

    # ── Step helpers ──────────────────────────────────────────────────────────
    # Steps are stored as an embedded list on the Workflow item.
    # These helpers load the item, mutate the steps list, and write it back.

    def add_step(self, workflow_id: str, step: dict[str, Any]) -> dict[str, Any] | None:
        """Append a step to the workflow's steps list."""
        workflow = self.get(workflow_id)
        if not workflow:
            return None
        steps: list = workflow.get("steps", [])
        steps.append(step)
        return self.update(workflow_id, {"steps": steps})

    def replace_step(
        self, workflow_id: str, step_id: str, new_step: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Fully replace a step (PUT semantics).
        new_step must contain all required fields including stepId.
        Using full replacement avoids stale fields when the step type changes
        (e.g. AGENT → LLM would otherwise retain orphaned agentId / inputMapping).
        """
        workflow = self.get(workflow_id)
        if not workflow:
            return None
        steps: list = workflow.get("steps", [])
        for i, s in enumerate(steps):
            if s.get("stepId") == step_id:
                steps[i] = new_step
                return self.update(workflow_id, {"steps": steps})
        return None

    def delete_step(self, workflow_id: str, step_id: str) -> dict[str, Any] | None:
        """Remove a step from the steps list by stepId."""
        workflow = self.get(workflow_id)
        if not workflow:
            return None
        steps = [s for s in workflow.get("steps", []) if s.get("stepId") != step_id]
        return self.update(workflow_id, {"steps": steps})

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(workflow_id), "SK": self.SK}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_author(self, author_id: str) -> list[dict[str, Any]]:
        """
        GSI1_AuthorByDate: all WORKFLOW items for this author, sorted by createdAt asc.
        """
        resp = self._table.query(
            IndexName="GSI1_AuthorByDate",
            KeyConditionExpression=Key("authorId").eq(author_id),
            FilterExpression=Attr("entityType").eq("WORKFLOW"),
        )
        return [self._clean(item) for item in resp.get("Items", [])]
