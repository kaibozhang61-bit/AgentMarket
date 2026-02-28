"""
Workflow router — /workflows

⚠️  Route ordering:
    GET /workflows/me  MUST be declared before  GET /workflows/{workflow_id}
    for the same reason as in the agents router.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUserId
from app.models.workflow import (
    StepBody,
    WorkflowCreateRequest,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdateRequest,
    WorkflowValidateResponse,
)
from app.services.workflow_service import WorkflowService

router = APIRouter()


def _svc() -> WorkflowService:
    return WorkflowService()


WorkflowServiceDep = Annotated[WorkflowService, Depends(_svc)]


# ── GET /workflows/me  ────────────────────────────────────────────────────────
# Declared first — see module docstring.

@router.get(
    "/me",
    response_model=WorkflowListResponse,
    summary="List my workflows",
)
def list_my_workflows(
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowListResponse:
    """Return all workflows created by the authenticated user."""
    workflows = svc.list_mine(current_user_id)
    return WorkflowListResponse(workflows=workflows, total=len(workflows))


# ── POST /workflows  ──────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow",
)
def create_workflow(
    body: WorkflowCreateRequest,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """Create a new workflow draft with an empty steps list."""
    return svc.create(current_user_id, body)  # type: ignore[return-value]


# ── GET /workflows/{workflow_id}  ─────────────────────────────────────────────

@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow detail",
)
def get_workflow(
    workflow_id: str,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """Return full workflow detail including all steps. Only the owner can access."""
    return svc.get(workflow_id, current_user_id)  # type: ignore[return-value]


# ── PUT /workflows/{workflow_id}  ─────────────────────────────────────────────

@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow metadata",
)
def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateRequest,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """Update workflow name, description, context, or status."""
    return svc.update(workflow_id, current_user_id, body)  # type: ignore[return-value]


# ── DELETE /workflows/{workflow_id}  ─────────────────────────────────────────

@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete workflow",
)
def delete_workflow(
    workflow_id: str,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> None:
    """Permanently delete a workflow and all its steps."""
    svc.delete(workflow_id, current_user_id)


# ── POST /workflows/{workflow_id}/validate  ───────────────────────────────────

@router.post(
    "/{workflow_id}/validate",
    response_model=WorkflowValidateResponse,
    summary="Validate workflow schema compatibility",
)
def validate_workflow(
    workflow_id: str,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowValidateResponse:
    """
    Check whether all required Agent input fields can be resolved from:
    - inputMapping / missingFieldsResolution set by the user
    - workflow context variables
    - output fields produced by earlier steps

    Returns a list of issues with suggestions for fixing each one.
    """
    return svc.validate(workflow_id, current_user_id)  # type: ignore[return-value]


# ── POST /workflows/{workflow_id}/steps  ─────────────────────────────────────

@router.post(
    "/{workflow_id}/steps",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add step to workflow",
)
def add_step(
    workflow_id: str,
    body: StepBody,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """
    Add a new step to the workflow.

    Supported step types (set `type` field to select):
    - **AGENT**: invoke a marketplace agent
    - **LLM**: call Claude directly with a prompt template
    - **LOGIC**: conditional branching, data transformation, or user-input pause
    """
    return svc.add_step(workflow_id, current_user_id, body)  # type: ignore[return-value]


# ── PUT /workflows/{workflow_id}/steps/{step_id}  ────────────────────────────

@router.put(
    "/{workflow_id}/steps/{step_id}",
    response_model=WorkflowResponse,
    summary="Replace a step",
)
def replace_step(
    workflow_id: str,
    step_id: str,
    body: StepBody,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """
    Fully replace an existing step (PUT semantics — all step fields are overwritten).
    Use this to change step configuration or switch step type entirely.
    The stepId is taken from the URL; any stepId in the body is ignored.
    """
    return svc.replace_step(workflow_id, step_id, current_user_id, body)  # type: ignore[return-value]


# ── DELETE /workflows/{workflow_id}/steps/{step_id}  ─────────────────────────

@router.delete(
    "/{workflow_id}/steps/{step_id}",
    response_model=WorkflowResponse,
    summary="Delete a step",
)
def delete_step(
    workflow_id: str,
    step_id: str,
    current_user_id: CurrentUserId,
    svc: WorkflowServiceDep,
) -> WorkflowResponse:
    """Remove a step from the workflow. Returns the updated workflow."""
    return svc.delete_step(workflow_id, step_id, current_user_id)  # type: ignore[return-value]
