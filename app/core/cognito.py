"""
app/core/cognito.py

Cognito JWT verification using RS256 + JWKS.

Behaviour
---------
* COGNITO_USER_POOL_ID is set  →  full RS256 + claims verification via JWKS.
* COGNITO_USER_POOL_ID is empty →  dev/test mode: base64-decode without
  signature verification.  A warning is printed at startup.

Token types accepted
--------------------
* ID token     (token_use=id)      — issued after login, contains email.
* Access token (token_use=access)  — for API calls; no email claim.

PyJWKClient caches the JWKS in memory and re-fetches only when a kid is
not found in the local cache (automatic key rotation handling).
"""

from __future__ import annotations

import base64
import json
import warnings
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWTError

from app.core.config import get_settings

# Module-level singleton — initialised lazily on first token verification.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        settings = get_settings()
        url = (
            f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
            f"/{settings.cognito_user_pool_id}/.well-known/jwks.json"
        )
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def verify_token(token: str) -> dict[str, Any]:
    """
    Verify a Cognito JWT and return its decoded claims.

    Raises jwt.PyJWTError (or a subclass) on any failure:
      - expired token
      - invalid signature
      - wrong issuer / audience / token_use
      - malformed token
    """
    settings = get_settings()

    if not settings.cognito_user_pool_id:
        warnings.warn(
            "COGNITO_USER_POOL_ID is not set — running in dev mode with "
            "NO signature verification. Never use this in production.",
            stacklevel=2,
        )
        return _dev_decode(token)

    return _verify_with_jwks(token, settings)


def _verify_with_jwks(token: str, settings: Any) -> dict[str, Any]:
    """Full RS256 + claims verification against Cognito JWKS."""
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)

    # verify_aud=False because access tokens have no 'aud' claim;
    # we check client_id / aud manually below.
    claims: dict[str, Any] = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )

    # ── Issuer ────────────────────────────────────────────────────────────────
    expected_iss = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
        f"/{settings.cognito_user_pool_id}"
    )
    if claims.get("iss") != expected_iss:
        raise PyJWTError(
            f"Token issuer {claims.get('iss')!r} does not match User Pool"
        )

    # ── Token use ─────────────────────────────────────────────────────────────
    token_use = claims.get("token_use")
    if token_use not in ("access", "id"):
        raise PyJWTError(f"Unexpected token_use: {token_use!r}")

    # ── Audience / client_id ──────────────────────────────────────────────────
    if settings.cognito_client_id:
        if token_use == "access":
            if claims.get("client_id") != settings.cognito_client_id:
                raise PyJWTError("Access token client_id does not match app client")
        elif token_use == "id":
            if claims.get("aud") != settings.cognito_client_id:
                raise PyJWTError("ID token audience does not match app client")

    return claims


def _dev_decode(token: str) -> dict[str, Any]:
    """
    Decode JWT payload WITHOUT signature verification.
    For local development only.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise PyJWTError("Malformed JWT: expected 3 dot-separated segments")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception as exc:
        raise PyJWTError(f"Cannot decode token payload: {exc}") from exc
