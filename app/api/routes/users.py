"""
Users router — mounted at /users
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUserClaims, CurrentUserId
from app.models.user import UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter()


def _svc() -> UserService:
    return UserService()


UserServiceDep = Annotated[UserService, Depends(_svc)]


# ── GET /users/me  ────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get my profile",
)
def get_me(
    current_user_id: CurrentUserId,
    claims: CurrentUserClaims,
    svc: UserServiceDep,
) -> UserResponse:
    """
    Return the current user's profile.

    On first call after Cognito sign-up, the DDB record is created
    automatically from the JWT claims (lazy provisioning).
    """
    user = svc.get_me(current_user_id, claims)
    return UserResponse(**user)


# ── PUT /users/me  ────────────────────────────────────────────────────────────

@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update my profile",
)
def update_me(
    body: UserUpdateRequest,
    current_user_id: CurrentUserId,
    svc: UserServiceDep,
) -> UserResponse:
    """Update mutable profile fields (currently: username)."""
    user = svc.update_me(current_user_id, body.model_dump())
    return UserResponse(**user)
