"""
FastAPI dependency functions shared across all route modules.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWTError

from app.core.cognito import verify_token


def get_current_user_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """
    Verify the Bearer token and return the full JWT claims dict.

    Raises HTTP 401 if the header is missing or the token is invalid.
    All other auth dependencies delegate to this one, so the token is
    verified exactly once per request (FastAPI deduplicates dependencies
    by function reference).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        return verify_token(token)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(
    claims: Annotated[dict[str, Any], Depends(get_current_user_claims)],
) -> str:
    """Extract the Cognito userId (JWT 'sub' claim) from verified claims."""
    user_id: str | None = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


# ── Convenient type aliases for route signatures ───────────────────────────────

# Full claims dict — use when the route needs email / username from the token
# (e.g. GET /users/me auto-creates the DDB record on first login).
CurrentUserClaims = Annotated[dict[str, Any], Depends(get_current_user_claims)]

# Just the userId string — use for all other protected routes.
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
