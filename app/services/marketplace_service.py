"""
MarketplaceService — business logic for public Agent discovery.

Rules:
  - Only published + public agents are visible.
  - No auth required (public endpoints).
  - Pagination is handled in-memory after fetching all matching items from DDB.
    This is acceptable for MVP scale; swap for server-side pagination later.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, status

from app.dao.agent_dao import AgentDAO

SortField = Literal["callCount", "createdAt"]


class MarketplaceService:

    def __init__(self) -> None:
        self._dao = AgentDAO()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _paginate(
        items: list[dict[str, Any]], page: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Slice a list into one page; return (page_items, total)."""
        total = len(items)
        start = (page - 1) * limit
        return items[start : start + limit], total

    # ── Public methods ────────────────────────────────────────────────────────

    def list_agents(
        self,
        page: int = 1,
        limit: int = 20,
        sort: SortField = "callCount",
    ) -> dict[str, Any]:
        """
        Return a paginated list of published+public agents.

        sort=callCount  — ordered by GSI2 (hottest first); no extra work needed.
        sort=createdAt  — re-sorted in memory after fetching from GSI2.
        """
        all_agents = self._dao.list_all_marketplace()

        if sort == "createdAt":
            all_agents.sort(key=lambda a: a.get("createdAt", ""), reverse=True)
        # sort=callCount: GSI2 already returns items sorted by callCount desc

        page_items, total = self._paginate(all_agents, page, limit)
        return {"agents": page_items, "total": total, "page": page}

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """
        Return a single published+public agent.
        Returns 404 for private or non-existent agents to avoid leaking existence.
        """
        agent = self._dao.get(agent_id)
        if (
            not agent
            or agent.get("status") != "published"
            or agent.get("visibility") != "public"
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
        return agent

    def search_agents(
        self,
        keyword: str,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Keyword search across agent name and description.
        Results are returned sorted by callCount desc (most popular first).
        """
        all_results = self._dao.search(keyword)
        # Sort matches by callCount so the most relevant/popular appear first
        all_results.sort(key=lambda a: a.get("callCount", 0), reverse=True)

        page_items, total = self._paginate(all_results, page, limit)
        return {"agents": page_items, "total": total, "page": page}
