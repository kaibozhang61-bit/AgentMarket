"""
Pydantic schemas for the WorkflowRun module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepResultItem(BaseModel):
    """Result of one step execution, embedded in the run record."""
    stepId: str
    type: str                                          # AGENT | LLM | LOGIC
    status: str                                        # success | failed | skipped | waiting_user_input
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None
    # Set only when status=waiting_user_input
    pendingQuestion: str | None = None
    outputField: str | None = None                     # field name expected from the resume answer


class RunResponse(BaseModel):
    runId: str
    workflowId: str
    triggeredBy: str
    status: str                                        # running | success | failed | waiting_user_input
    stepResults: list[StepResultItem]
    startedAt: str
    finishedAt: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int


class ResumeRequest(BaseModel):
    """Body for POST /workflows/{workflowId}/runs/{runId}/resume"""
    answer: Any    # the user's response to the pendingQuestion
