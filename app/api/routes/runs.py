"""
Agent Run router — mounted at /agents

All run endpoints are nested under /agents/{agent_id}/...
and require the caller to own the parent agent.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import CurrentUserId
from app.models.run import ResumeRequest, RunListResponse, RunResponse
from app.services.run_service import RunService

router = APIRouter()


def _svc() -> RunService:
    return RunService()


RunServiceDep = Annotated[RunService, Depends(_svc)]


# ── POST /agents/{agent_id}/run  ─────────────────────────────────────────────

@router.post(
    "/{agent_id}/run",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger agent execution",
)
def trigger_run(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """
    Start an asynchronous agent execution.

    Returns immediately with status=running and the new runId.
    Steps execute in the background in order.
    Poll GET /agents/{agent_id}/runs/{runId} to track progress.
    """
    run = svc.trigger_run(agent_id, current_user_id)
    background_tasks.add_task(svc.execute_run, agent_id, run["runId"], current_user_id)
    return RunResponse(**run)


# ── GET /agents/{agent_id}/runs  ─────────────────────────────────────────────

@router.get(
    "/{agent_id}/runs",
    response_model=RunListResponse,
    summary="List agent runs",
)
def list_runs(
    agent_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunListResponse:
    """Return the most recent runs for an agent, newest first."""
    result = svc.list_runs(agent_id, current_user_id, limit=limit)
    return RunListResponse(**result)


# ── GET /agents/{agent_id}/runs/{run_id}  ────────────────────────────────────

@router.get(
    "/{agent_id}/runs/{run_id}",
    response_model=RunResponse,
    summary="Get run detail",
)
def get_run(
    agent_id: str,
    run_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
) -> RunResponse:
    """Return full run detail including per-step input, output, latency."""
    return svc.get_run(agent_id, run_id, current_user_id)  # type: ignore[return-value]


# ── POST /agents/{agent_id}/runs/{run_id}/resume  ────────────────────────────

@router.post(
    "/{agent_id}/runs/{run_id}/resume",
    response_model=RunResponse,
    summary="Resume a paused run",
)
def resume_run(
    agent_id: str,
    run_id: str,
    body: ResumeRequest,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """
    Provide the answer to a pending user-input question and continue execution.
    Returns immediately with status=running.
    """
    run = svc.resume_run(agent_id, run_id, current_user_id, body.answer)
    background_tasks.add_task(svc.continue_run, agent_id, run_id, current_user_id)
    return RunResponse(**run)

# NOTE: resume is kept for future interactive step support.
# Currently no step type produces waiting_user_input status.
