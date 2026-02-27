"""
Marketplace router — /marketplace

All endpoints are public (no auth required).

⚠️  Route ordering matters:
    GET /agents/search  MUST be declared before  GET /agents/{agent_id}.
    FastAPI matches routes in order; without this, the literal string
    "search" would be captured as the {agent_id} path parameter.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.models.marketplace import MarketplaceAgentItem, MarketplaceListResponse
from app.services.marketplace_service import MarketplaceService

router = APIRouter()


def _svc() -> MarketplaceService:
    return MarketplaceService()


MarketplaceServiceDep = Annotated[MarketplaceService, Depends(_svc)]


# ── GET /marketplace/agents/search  ──────────────────────────────────────────
# Declared first — see module docstring.

@router.get(
    "/agents/search",
    response_model=MarketplaceListResponse,
    summary="Search agents by keyword",
)
def search_agents(
    svc: MarketplaceServiceDep,
    q: Annotated[str, Query(min_length=1, description="Search keyword")],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MarketplaceListResponse:
    """
    Full-text search across agent name and description.
    Results sorted by callCount desc (most popular first).
    """
    result = svc.search_agents(q, page=page, limit=limit)
    return MarketplaceListResponse(**result)


# ── GET /marketplace/agents  ──────────────────────────────────────────────────

@router.get(
    "/agents",
    response_model=MarketplaceListResponse,
    summary="Browse marketplace agents",
)
def list_agents(
    svc: MarketplaceServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Annotated[Literal["callCount", "createdAt"], Query()] = "callCount",
) -> MarketplaceListResponse:
    """
    Browse all published public agents.

    - **sort=callCount** (default): hottest agents first (via GSI2, efficient).
    - **sort=createdAt**: newest agents first (in-memory sort).
    """
    result = svc.list_agents(page=page, limit=limit, sort=sort)
    return MarketplaceListResponse(**result)


# ── GET /marketplace/agents/{agent_id}  ──────────────────────────────────────

@router.get(
    "/agents/{agent_id}",
    response_model=MarketplaceAgentItem,
    summary="Get marketplace agent detail",
)
def get_agent(
    agent_id: str,
    svc: MarketplaceServiceDep,
) -> MarketplaceAgentItem:
    """
    Return the public detail of a single published agent.
    Returns 404 for private, draft, or non-existent agents.
    """
    return svc.get_agent(agent_id)  # type: ignore[return-value]
