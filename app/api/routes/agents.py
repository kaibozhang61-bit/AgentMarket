"""
Agent router — /agents

⚠️  Route ordering matters:
    GET /agents/me  MUST be declared before  GET /agents/{agent_id}.
    FastAPI matches routes in declaration order; without this, the literal
    string "me" would be captured as the {agent_id} path parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUserId
from app.models.agent import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    AgentTestRequest,
    AgentTestStepRequest,
    AgentTestResponse,
    AgentUpdateRequest,
    AgentValidateResponse,
)
from app.models.agent_chat import AgentChatRequest, AgentChatResponse
from app.services.agent_service import AgentService
from app.services.agent_chat_service import AgentChatService

router = APIRouter()


def _svc() -> AgentService:
    return AgentService()


def _chat_svc() -> AgentChatService:
    return AgentChatService()


AgentServiceDep = Annotated[AgentService, Depends(_svc)]
AgentChatServiceDep = Annotated[AgentChatService, Depends(_chat_svc)]


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


# ── POST /agents/chat  ───────────────────────────────────────────────────────
# Declared before /{agent_id} so "chat" is not captured as a path param.

@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="LLM-driven agent creation chat",
)
def agent_chat(
    body: AgentChatRequest,
    current_user_id: CurrentUserId,
    svc: AgentChatServiceDep,
) -> AgentChatResponse:
    """
    4-stage conversational agent builder.

    On the first call, omit sessionId and agentId — the backend creates both.
    On subsequent calls, send back the sessionId and agentId from the
    previous response so the backend can resume the conversation.
    """
    result = svc.chat(
        user_id=current_user_id,
        message=body.message,
        session_id=body.sessionId,
        agent_id=body.agentId,
    )
    return AgentChatResponse(**result)


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


# ── POST /agents/{agent_id}/verify-publish  ──────────────────────────────────

@router.post(
    "/{agent_id}/verify-publish",
    status_code=status.HTTP_200_OK,
    summary="LLM-verify then publish",
)
def verify_publish_agent(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> dict:
    """
    LLM reviews the agent for issues before publishing.
    If safe, publishes automatically. If concerns found, returns them
    without publishing — user can fix and reverify or override.
    """
    return svc.verify_for_publish(agent_id, current_user_id)


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


# ── POST /agents/{agent_id}/test-step  ───────────────────────────────────────

@router.post(
    "/{agent_id}/test-step",
    response_model=AgentTestResponse,
    summary="Test a single step with sample input",
)
def test_step(
    agent_id: str,
    body: AgentTestStepRequest,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentTestResponse:
    """
    Run a single step in isolation using Claude Haiku.
    Ephemeral — results are not persisted.
    Only LLM steps are supported; agent steps return 400.
    """
    return svc.test_step(agent_id, current_user_id, body.stepId, body.input)  # type: ignore[return-value]


# ── POST /agents/{agent_id}/validate  ────────────────────────────────────────

@router.post(
    "/{agent_id}/validate",
    response_model=AgentValidateResponse,
    summary="Validate agent schema compatibility",
)
def validate_agent(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentValidateResponse:
    """
    Check whether all required input fields for each step can be resolved
    from context, inputMapping, missingFieldsResolution, or outputs of
    earlier steps. Returns a list of issues with suggestions for fixing.
    """
    return svc.validate(agent_id, current_user_id)  # type: ignore[return-value]


# ── GET /agents/{agent_id}/session  ──────────────────────────────────────────

@router.get(
    "/{agent_id}/session",
    status_code=status.HTTP_200_OK,
    summary="Get latest chat session for an agent",
)
def get_agent_session(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
    chat_svc: AgentChatServiceDep,
) -> dict:
    """
    Return the latest chat session for a draft agent so the user can
    resume the conversation. Returns 404 if no session exists.
    """
    agent = svc.get(agent_id, current_user_id)
    from app.dao.agent_chat_session_dao import AgentChatSessionDAO
    session_dao = AgentChatSessionDAO()
    session = session_dao.get_latest(agent_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No chat session found for this agent",
        )
    # Return only what the frontend needs — extract display message from raw JSON
    history = session.get("history", [])

    def _extract_display(role: str, content: str) -> str:
        """For assistant messages, extract the 'message' field from raw JSON."""
        if role == "user":
            return content
        import json as _json
        import re as _re
        cleaned = _re.sub(r"^```(?:json)?\s*", "", content.strip()).rstrip("`").strip()
        try:
            parsed = _json.loads(cleaned)
            if isinstance(parsed, dict) and "message" in parsed:
                return parsed["message"]
        except (ValueError, _json.JSONDecodeError):
            pass
        return content

    return {
        "sessionId": session["sessionId"],
        "agentId": agent_id,
        "stage": session.get("stage", "clarifying"),
        "messages": [
            {"role": m["role"], "content": _extract_display(m["role"], m["content"])}
            for m in history
        ],
    }


# ── PUT /agents/{agent_id}/draft  ────────────────────────────────────────────

@router.put(
    "/{agent_id}/draft",
    response_model=AgentResponse,
    summary="Auto-save agent draft",
)
def auto_save_draft(
    agent_id: str,
    body: AgentUpdateRequest,
    current_user_id: CurrentUserId,
    svc: AgentServiceDep,
) -> AgentResponse:
    """
    Auto-save endpoint for Quip-style continuous saving.
    Same as PUT /agents/{agentId} but semantically distinct —
    called by the frontend debounce timer, not by explicit user action.
    """
    return svc.update(agent_id, current_user_id, body)  # type: ignore[return-value]
