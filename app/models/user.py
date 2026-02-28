"""
Pydantic schemas for the User module.
"""

from __future__ import annotations

from pydantic import BaseModel


class UserResponse(BaseModel):
    userId: str
    email: str
    username: str
    createdAt: str
    updatedAt: str


class UserUpdateRequest(BaseModel):
    """Only mutable fields. Omit a field to leave it unchanged."""
    username: str | None = None
