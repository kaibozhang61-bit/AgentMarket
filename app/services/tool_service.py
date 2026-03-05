"""
ToolService — manages external tool integrations.

Each tool has a standard inputSchema/outputSchema, authenticates via
user-provided credentials (stored in Secrets Manager), and runs in
isolated Lambda with timeout.
"""

from __future__ import annotations

from typing import Any

from app.dao.tool_registry_dao import ToolRegistryDAO


class ToolService:

    def __init__(self) -> None:
        self._dao = ToolRegistryDAO()

    def list_tools(self) -> list[dict[str, Any]]:
        return self._dao.list_all()

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        return self._dao.get(tool_id)

    def register_tool(self, tool_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._dao.create(tool_id, data)
