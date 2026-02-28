"""
WorkflowRun router — mounted at /workflows

All four run endpoints are nested under /workflows/{workflow_id}/...
and require the caller to own the parent workflow.
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


# ── POST /workflows/{workflow_id}/run  ────────────────────────────────────────

@router.post(
    "/{workflow_id}/run",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger workflow execution",
)
def trigger_run(
    workflow_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """
    Start an asynchronous workflow execution.

    Returns immediately with status=running and the new runId.
    Steps execute in the background in `order` sequence.
    Poll GET /{workflow_id}/runs/{runId} to track progress.
    """
    run = svc.trigger_run(workflow_id, current_user_id)
    background_tasks.add_task(svc.execute_run, workflow_id, run["runId"], current_user_id)
    return RunResponse(**run)


# ── GET /workflows/{workflow_id}/runs  ────────────────────────────────────────

@router.get(
    "/{workflow_id}/runs",
    response_model=RunListResponse,
    summary="List workflow runs",
)
def list_runs(
    workflow_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunListResponse:
    """Return the most recent runs for a workflow, newest first."""
    result = svc.list_runs(workflow_id, current_user_id, limit=limit)
    return RunListResponse(**result)


# ── GET /workflows/{workflow_id}/runs/{run_id}  ───────────────────────────────

@router.get(
    "/{workflow_id}/runs/{run_id}",
    response_model=RunResponse,
    summary="Get run detail",
)
def get_run(
    workflow_id: str,
    run_id: str,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
) -> RunResponse:
    """
    Return the full run detail including per-step input, output, latency,
    and any pending question when the run is paused.
    """
    return svc.get_run(workflow_id, run_id, current_user_id)  # type: ignore[return-value]


# ── POST /workflows/{workflow_id}/runs/{run_id}/resume  ───────────────────────

@router.post(
    "/{workflow_id}/runs/{run_id}/resume",
    response_model=RunResponse,
    summary="Resume a paused run",
)
def resume_run(
    workflow_id: str,
    run_id: str,
    body: ResumeRequest,
    current_user_id: CurrentUserId,
    svc: RunServiceDep,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """
    Provide the answer to a pending user-input question and continue execution.

    Returns immediately with status=running.
    Remaining steps execute in the background.
    Poll GET /{workflow_id}/runs/{runId} to track progress.
    """
    run = svc.resume_run(workflow_id, run_id, current_user_id, body.answer)
    background_tasks.add_task(svc.continue_run, workflow_id, run_id, current_user_id)
    return RunResponse(**run)
