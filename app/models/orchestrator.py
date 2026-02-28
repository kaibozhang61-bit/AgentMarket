"""
Pydantic schemas for the Orchestrator module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Body for POST /orchestrator/chat"""
    message: str


class ChatResponse(BaseModel):
    """
    Response from draft_workflow:
      type        always "DRAFT_WORKFLOW"
      workflowName  suggested workflow name
      draftSteps    list of step definitions for the canvas
      usedAgentIds  marketplace agent IDs referenced in the draft
      summary       one-sentence description of the workflow
    """
    type: str
    workflowName: str | None = None
    draftSteps: list[dict[str, Any]] = []
    usedAgentIds: list[str] = []
    summary: str | None = None
