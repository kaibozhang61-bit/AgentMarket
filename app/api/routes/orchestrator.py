"""
Orchestrator router — mounted at /orchestrator
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUserId
from app.models.orchestrator import ChatRequest, ChatResponse
from app.services.orchestrator_service import OrchestratorService

router = APIRouter()


def _svc() -> OrchestratorService:
    return OrchestratorService()


OrchestratorServiceDep = Annotated[OrchestratorService, Depends(_svc)]


# ── POST /orchestrator/chat  ──────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a workflow draft from natural language",
)
def chat(
    body: ChatRequest,
    current_user_id: CurrentUserId,
    svc: OrchestratorServiceDep,
) -> ChatResponse:
    """
    Accepts a natural-language description and returns a workflow draft
    (step definitions) for the canvas. No agents are executed.
    """
    result = svc.draft_workflow(body.message)
    return ChatResponse(**result)
