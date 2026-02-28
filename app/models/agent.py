"""
Pydantic schemas for the Agent module.

Agent types
-----------
Simple agent   — steps list with exactly 1 step of type="llm"
Composite agent — steps list with 2+ steps (type="llm" or type="agent")

systemPrompt no longer lives at the top level; it is a field inside
each type="llm" step.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ── Shared sub-schema ─────────────────────────────────────────────────────────

class FieldSchema(BaseModel):
    """One field in an Agent's inputSchema or outputSchema."""
    fieldName: str
    type: str                   # string | number | boolean | list<string> | object
    required: bool = True
    default: Any = None
    description: str = ""


# ── Step types ────────────────────────────────────────────────────────────────

class LLMStep(BaseModel):
    """A step that calls an LLM directly with a system prompt."""
    stepId: str = ""            # auto-assigned by DAO if empty
    order: int
    type: Literal["llm"]
    systemPrompt: str
    inputSchema: list[FieldSchema] = Field(default_factory=list)
    outputSchema: list[FieldSchema] = Field(default_factory=list)
    transformMode: str = "auto"
    inputMapping: dict[str, str] = Field(default_factory=dict)
    missingFieldsResolution: dict[str, Any] = Field(default_factory=dict)


class AgentRefStep(BaseModel):
    """A step that delegates to another Agent in the marketplace."""
    stepId: str = ""            # auto-assigned by DAO if empty
    order: int
    type: Literal["agent"]
    agentId: str
    transformMode: str = "auto"
    inputMapping: dict[str, str] = Field(default_factory=dict)
    missingFieldsResolution: dict[str, Any] = Field(default_factory=dict)


# Discriminated union — Pydantic picks the right model based on "type" field
Step = Annotated[Union[LLMStep, AgentRefStep], Field(discriminator="type")]


# ── Request bodies ────────────────────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    steps: list[Step] = Field(min_length=1)   # at least 1 step required
    inputSchema: list[FieldSchema] = Field(default_factory=list)
    outputSchema: list[FieldSchema] = Field(default_factory=list)
    visibility: Literal["public", "private"] = "private"
    toolsRequired: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    """All fields are optional — only provided fields are updated."""
    name: str | None = None
    description: str | None = None
    steps: list[Step] | None = None
    inputSchema: list[FieldSchema] | None = None
    outputSchema: list[FieldSchema] | None = None
    visibility: Literal["public", "private"] | None = None
    toolsRequired: list[str] | None = None


class AgentTestRequest(BaseModel):
    input: dict[str, Any]


# ── Responses ─────────────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    agentId: str
    name: str
    description: str
    authorId: str
    status: str
    visibility: str
    version: str
    steps: list[dict[str, Any]]
    inputSchema: list[dict[str, Any]]
    outputSchema: list[dict[str, Any]]
    toolsRequired: list[str]
    callCount: int
    lastUsedAt: str | None = None
    createdAt: str
    updatedAt: str
    # Incremental 2
    level: str = "L1"
    tools: list[dict[str, Any]] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int


class AgentTestResponse(BaseModel):
    output: dict[str, Any]
    latency_ms: int
