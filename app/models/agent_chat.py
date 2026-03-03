"""
Pydantic schemas for the Agent Chat module (POST /agents/chat).

4-stage creation flow:
  clarifying → confirming → planning → editing → saved
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """Body for POST /agents/chat"""
    message: str
    sessionId: str | None = None   # null on first message → backend creates session
    agentId: str | None = None     # null on first message → backend creates draft agentId


class DraftPayload(BaseModel):
    """Agent draft returned during planning / editing stages."""
    name: str = ""
    description: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    inputSchema: list[dict[str, Any]] = Field(default_factory=list)
    outputSchema: list[dict[str, Any]] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    """Response from POST /agents/chat"""
    sessionId: str
    agentId: str                   # draft agentId — frontend must send this back
    stage: str                     # clarifying | confirming | planning | editing | saved
    message: str                   # LLM reply to show the user
    draft: DraftPayload | None = None
