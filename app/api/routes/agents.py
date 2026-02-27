"""
Agent router — /agents

⚠️  Route ordering matters:
    GET /agents/me  MUST be declared before  GET /agents/{agent_id}.
    FastAPI matches routes in declaration order; without this, the literal
    string "me" would be captured as the {agent_id} path parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUserId
from app.models.agent import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    AgentTestRequest,
    AgentTestResponse,
    AgentUpdateRequest,
)
from app.services.agent_service import AgentService

router = APIRouter()


def _svc() -> AgentService:
    return AgentService()


AgentServiceDep = Annotated[AgentService, Depends(_svc)]


# ── GET /agents/me  ───────────────────────────────────────────────────────────
# Declared first — see module docstring.

@router.get(
    "/me",
    response_model=AgentListResponse,
    summary="List my agents",
)
def list_my_agents(
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentListResponse:
    """Return all agents created by the authenticated user."""
    agents = svc.list_mine(current_user_id)
    return AgentListResponse(agents=agents, total=len(agents))


# ── POST /agents  ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent",
)
def create_agent(
    body: AgentCreateRequest,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentResponse:
    """Create a new agent draft owned by the current user."""
    return svc.create(current_user_id, body)  # type: ignore[return-value]


# ── GET /agents/{agent_id}  ───────────────────────────────────────────────────

@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent detail",
)
def get_agent(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentResponse:
    """Return full agent detail. Only the owner can access this endpoint."""
    return svc.get(agent_id, current_user_id)  # type: ignore[return-value]


# ── PUT /agents/{agent_id}  ───────────────────────────────────────────────────

@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update agent",
)
def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentResponse:
    """Update one or more fields of an agent. Only the owner can update."""
    return svc.update(agent_id, current_user_id, body)  # type: ignore[return-value]


# ── DELETE /agents/{agent_id}  ────────────────────────────────────────────────

@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete agent",
)
def delete_agent(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> None:
    """Permanently delete an agent. Only the owner can delete."""
    svc.delete(agent_id, current_user_id)


# ── POST /agents/{agent_id}/publish  ─────────────────────────────────────────

@router.post(
    "/{agent_id}/publish",
    response_model=AgentResponse,
    summary="Publish agent to marketplace",
)
def publish_agent(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentResponse:
    """
    Transition the agent from draft → published.
    Sets statusVisibility so it appears in the marketplace GSI.
    Idempotent — safe to call multiple times.
    """
    return svc.publish(agent_id, current_user_id)  # type: ignore[return-value]


# ── POST /agents/{agent_id}/test  ────────────────────────────────────────────

@router.post(
    "/{agent_id}/test",
    response_model=AgentTestResponse,
    summary="Test agent with sample input",
)
def test_agent(
    agent_id: str,
    body: AgentTestRequest,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentTestResponse:
    """
    Run the agent against the provided input using Claude Haiku.
    Returns the model output and wall-clock latency in milliseconds.
    """
    return svc.test(agent_id, current_user_id, body.input)  # type: ignore[return-value]
