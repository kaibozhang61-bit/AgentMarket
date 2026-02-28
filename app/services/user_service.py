"""
UserService — GET /users/me, PUT /users/me

Lazy provisioning
-----------------
DDB user records are created on the first GET /users/me call after
Cognito sign-up (no Lambda trigger needed).  Email and username are
taken from the JWT claims (present in ID tokens; empty for access tokens).
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.dao.user_dao import UserDAO


class UserService:

    def __init__(self) -> None:
        self._dao = UserDAO()

    def get_me(self, user_id: str, claims: dict[str, Any]) -> dict[str, Any]:
        """
        Return the DDB profile for user_id, creating it on first login.

        Claims are used to seed email / username when the record doesn't
        exist yet.  Both fields come from the Cognito ID token; access
        tokens leave them empty (the user can fill them in via PUT /users/me).
        """
        user = self._dao.get(user_id)
        if user:
            return user

        # First login — auto-create from token claims
        email: str = claims.get("email") or ""
        username: str = (
            claims.get("cognito:username")
            or claims.get("username")
            or claims.get("preferred_username")
            or user_id   # fallback: use sub as username
        )

        try:
            return self._dao.create(user_id, {"email": email, "username": username})
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Concurrent request already created the record — just fetch it
                user = self._dao.get(user_id)
                if user:
                    return user
            raise

    def update_me(
        self, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update mutable profile fields. Raises 400 if nothing to update."""
        fields = {k: v for k, v in data.items() if v is not None}
        if not fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )
        try:
            return self._dao.update(user_id, fields)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found",
                )
            raise
