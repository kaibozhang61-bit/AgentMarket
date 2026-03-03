"""
Pydantic schemas for the Agent Run module.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StepResultItem(BaseModel):
    """Result of one step execution, embedded in the run record."""
    stepId: str
    type: str                                          # llm | agent
    status: str                                        # success | failed | skipped | waiting_user_input
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None
    pendingQuestion: str | None = None
    outputField: str | None = None


class BlackboardEntry(BaseModel):
    """One entry in the blackboard — written by agent_input or a step."""
    value: dict[str, Any] = Field(default_factory=dict)
    writtenBy: str = ""                                # stepId or "agent_input"
    writtenAt: str = ""
    publicBlackboard: dict[str, Any] = Field(default_factory=dict)  # only for type=agent steps


class RunResponse(BaseModel):
    runId: str
    agentId: str
    triggeredBy: str
    status: str                                        # running | success | failed | waiting_user_input
    stepResults: list[StepResultItem]
    blackboard: dict[str, Any] = Field(default_factory=dict)
    startedAt: str
    finishedAt: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunResponse]
    total: int


class ResumeRequest(BaseModel):
    """Body for POST /agents/{agentId}/runs/{runId}/resume"""
    answer: Any
