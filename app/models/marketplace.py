"""
Pydantic schemas for the Marketplace module.

The marketplace is a public read-only view — systemPrompt is intentionally
excluded so agent authors' IP is not exposed to other users.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.agent import FieldSchema


class MarketplaceAgentItem(BaseModel):
    """
    Public view of an Agent.
    Returned by both the list endpoint and the detail endpoint.
    """
    agentId: str
    name: str
    description: str
    authorId: str
    version: str
    status: str
    visibility: str
    inputSchema: list[FieldSchema]
    outputSchema: list[FieldSchema]
    callCount: int
    createdAt: str
    updatedAt: str
    # Incremental 2
    level: str = "L1"


class MarketplaceListResponse(BaseModel):
    agents: list[MarketplaceAgentItem]
    total: int
    page: int
