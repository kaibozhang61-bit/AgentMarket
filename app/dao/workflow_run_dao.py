"""
WorkflowRunDAO

DynamoDB layout:
  PK = WORKFLOW#<workflowId>      ← same PK as the parent Workflow
  SK = RUN#<runId>

Querying all runs for a workflow is a single DDB Query on PK with SK begins_with "RUN#".
This co-locates runs with their parent workflow for efficient retrieval.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from app.dao.base import BaseDAO


class WorkflowRunDAO(BaseDAO):

    @staticmethod
    def _pk(workflow_id: str) -> str:
        return f"WORKFLOW#{workflow_id}"

    @staticmethod
    def _sk(run_id: str) -> str:
        return f"RUN#{run_id}"

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, workflow_id: str, triggered_by: str) -> dict[str, Any]:
        """
        Create a new WorkflowRun with status=running.

        triggered_by: userId who triggered the run.
        """
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": self._pk(workflow_id),
            "SK": self._sk(run_id),
            "entityType": "WORKFLOW_RUN",
            "runId": run_id,
            "workflowId": workflow_id,
            "triggeredBy": triggered_by,
            "status": "running",   # running | success | failed | waiting_user_input
            "stepResults": [],
            "startedAt": now,
            "finishedAt": None,
        }
        self._table.put_item(Item=item)
        return self._clean(item)

    def update_status(
        self,
        workflow_id: str,
        run_id: str,
        status: str,
        step_results: list[dict] | None = None,
        finished: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update run status and optionally replace the full stepResults list.

        finished=True  → sets finishedAt to now (terminal states: success / failed).
        extra          → arbitrary additional fields to persist, e.g.
                         {"pendingStepId": "...", "pendingStepOrder": 2}
                         used to save pause state for the resume endpoint.
        """
        fields: dict[str, Any] = {"status": status}
        if step_results is not None:
            fields["stepResults"] = step_results
        if finished:
            fields["finishedAt"] = datetime.now(timezone.utc).isoformat()
        if extra:
            fields.update(extra)

        expr, names, values = self._build_update_expr(fields)
        resp = self._table.update_item(
            Key={"PK": self._pk(workflow_id), "SK": self._sk(run_id)},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    def append_step_result(
        self, workflow_id: str, run_id: str, step_result: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Append one StepResult to the stepResults list using DynamoDB list_append.
        More efficient than rewriting the entire list.
        """
        resp = self._table.update_item(
            Key={"PK": self._pk(workflow_id), "SK": self._sk(run_id)},
            UpdateExpression="SET stepResults = list_append(stepResults, :r)",
            ExpressionAttributeValues={":r": [step_result]},
            ReturnValues="ALL_NEW",
        )
        return self._clean(resp["Attributes"])

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, workflow_id: str, run_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(
            Key={"PK": self._pk(workflow_id), "SK": self._sk(run_id)}
        )
        item = resp.get("Item")
        return self._clean(item) if item else None

    def list_by_workflow(
        self, workflow_id: str, limit: int = 20, last_key: dict | None = None
    ) -> tuple[list[dict[str, Any]], dict | None]:
        """
        All runs for a workflow, newest first (SK desc).
        Returns (items, last_evaluated_key) for pagination.
        """
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": (
                Key("PK").eq(self._pk(workflow_id))
                & Key("SK").begins_with("RUN#")
            ),
            "ScanIndexForward": False,  # newest runs first
            "Limit": limit,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        resp = self._table.query(**kwargs)
        return (
            [self._clean(item) for item in resp.get("Items", [])],
            resp.get("LastEvaluatedKey"),
        )
