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


class SearchResult(BaseModel):
    """One agent from search results."""
    agent_id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    score: float = 0.0


class SearchResults(BaseModel):
    """Search results with path routing."""
    path: str = "no_results"  # direct | indirect | no_results
    results: list[SearchResult] = Field(default_factory=list)
    categories: list[dict[str, Any]] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    """Response from POST /agents/chat"""
    sessionId: str
    agentId: str
    stage: str  # clarifying | searching | path_a | path_b | path_c | planning | editing | saved
    message: str
    draft: DraftPayload | None = None
    searchResults: SearchResults | None = None
    selectedAgentId: str | None = None
    executionMode: str | None = None  # chat | form | hybrid
    executionInput: dict[str, Any] | None = None
    compositionAgents: list[str] | None = None
