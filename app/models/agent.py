"""
Pydantic schemas for the Agent module.

Used by:
  - routes layer  (request body / response serialization)
  - service layer (typed input parameters)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Shared sub-schema ─────────────────────────────────────────────────────────

class FieldSchema(BaseModel):
    """One field in an Agent's inputSchema or outputSchema."""
    fieldName: str
    type: str                   # string | number | boolean | list<string> | object
    required: bool = True
    default: Any = None
    description: str = ""


# ── Request bodies ────────────────────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    systemPrompt: str
    inputSchema: list[FieldSchema] = Field(default_factory=list)
    outputSchema: list[FieldSchema] = Field(default_factory=list)
    visibility: Literal["public", "private"] = "private"
    toolsRequired: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    """All fields are optional — only provided fields are updated."""
    name: str | None = None
    description: str | None = None
    systemPrompt: str | None = None
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
    systemPrompt: str
    inputSchema: list[FieldSchema]
    outputSchema: list[FieldSchema]
    toolsRequired: list[str]
    callCount: int
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
