"""
FastAPI dependency functions shared across all route modules.
"""

from __future__ import annotations

import base64
import json
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status


def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Extract the Cognito userId (JWT 'sub' claim) from the Authorization header.

    Expected header:
        Authorization: Bearer <cognito_id_token>

    Development note:
        Signature verification is intentionally skipped here — the payload is
        only base64-decoded. Before going to production, replace this function
        body with proper Cognito JWKS verification.

        Reference:
        https://docs.aws.amazon.com/cognito/latest/developerguide/
        amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("not a JWT")
        # Pad to a multiple of 4 for urlsafe_b64decode
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload: dict = json.loads(base64.urlsafe_b64decode(padded))
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise ValueError("missing sub claim")
        return user_id
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Convenient type alias for route signatures
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
