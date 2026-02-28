"""
Pydantic schemas for the Workflow module.

Step types use a discriminated union on the `type` field so FastAPI
automatically validates and documents the correct schema per type.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ── Step sub-schemas ──────────────────────────────────────────────────────────

class MissingFieldResolution(BaseModel):
    """How to satisfy a required agent input field that isn't in inputMapping."""
    source: Literal["context", "step", "fixed"]
    value: str  # e.g. "{{context.userId}}", "{{step1.output.field}}", "some fixed value"


class AgentStep(BaseModel):
    type: Literal["AGENT"]
    order: int
    agentId: str
    agentVersion: str = "1.0.0"
    transformMode: Literal["auto", "manual"] = "auto"
    # Explicit field-to-source mapping, e.g. {"topic": "{{context.custom_var}}"}
    inputMapping: dict[str, str] = Field(default_factory=dict)
    # Fallback resolution for required fields not covered by inputMapping
    missingFieldsResolution: dict[str, MissingFieldResolution] = Field(default_factory=dict)


class LLMStep(BaseModel):
    type: Literal["LLM"]
    order: int
    prompt: str  # May reference previous step outputs: {{step1.output.keywords}}
    # Single output field definition; None means raw text output
    outputSchema: dict[str, Any] | None = None  # {fieldName: str, type: str}


class LogicStep(BaseModel):
    type: Literal["LOGIC"]
    order: int
    logicType: Literal["condition", "transform", "user_input"]
    # Condition config: {"if": "{{step1.output.score}} > 0.8", "then": "step4", "else": "step5"}
    # Using dict to avoid Python reserved-word clash with `if`/`else`.
    condition: dict[str, str] | None = None
    # user_input type: question to display and field name to store the answer under
    question: str | None = None
    outputField: str | None = None


# Discriminated union — FastAPI picks the right model based on the `type` field
StepBody = Annotated[
    Union[AgentStep, LLMStep, LogicStep],
    Field(discriminator="type"),
]


# ── Workflow request / response ───────────────────────────────────────────────

class WorkflowCreateRequest(BaseModel):
    name: str
    description: str = ""
    # Global variables available to every step, e.g. {"userId": "{{current_user.id}}"}
    context: dict[str, str] = Field(default_factory=dict)


class WorkflowUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    context: dict[str, str] | None = None
    status: Literal["draft", "active"] | None = None


class WorkflowResponse(BaseModel):
    workflowId: str
    name: str
    description: str
    authorId: str
    context: dict[str, Any]
    steps: list[dict[str, Any]]   # stored as raw dicts; validated on write, returned as-is
    status: str
    createdAt: str
    updatedAt: str


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowResponse]
    total: int


# ── Validate response ─────────────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    stepId: str
    field: str
    issue: str
    suggestions: list[str]


class WorkflowValidateResponse(BaseModel):
    compatible: bool
    issues: list[ValidationIssue]
