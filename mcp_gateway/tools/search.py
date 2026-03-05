"""
search_agents MCP tool — 3-vector weighted kNN search with 3-path routing.
"""

from __future__ import annotations

from typing import Any

from mcp_gateway.config import THRESHOLD_DIRECT, THRESHOLD_INDIRECT
from mcp_gateway.embeddings import embed
from mcp_gateway.opensearch_client import knn_search


def search_agents(
    task_description: str,
    available_inputs: str = "",
    desired_outputs: str = "",
) -> dict[str, Any]:
    """
    Search the marketplace for agents matching the user's need.

    Returns:
      path: "direct" | "indirect" | "no_results"
      results: list of agents with scores
      categories: grouped results (for indirect path)
    """
    desc_vector = embed(task_description)
    input_vector = embed(available_inputs) if available_inputs else None
    output_vector = embed(desired_outputs) if desired_outputs else None

    if not desc_vector:
        return {"path": "no_results", "results": [], "categories": []}

    raw_results = knn_search(desc_vector, input_vector, output_vector)

    direct = [r for r in raw_results if r["score"] >= THRESHOLD_DIRECT]
    indirect = [r for r in raw_results if THRESHOLD_INDIRECT <= r["score"] < THRESHOLD_DIRECT]

    if direct:
        # Path A — cap at 5 + 1 free slot
        return {
            "path": "direct",
            "results": direct[:5],
            "categories": [],
        }

    if indirect:
        # Path B — group by category
        categories = _group_by_category(indirect)
        return {
            "path": "indirect",
            "results": indirect,
            "categories": categories,
        }

    # Path C — no match
    return {"path": "no_results", "results": [], "categories": []}


def _group_by_category(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group indirect results by category, sorted by max score."""
    groups: dict[str, dict[str, Any]] = {}
    for agent in results:
        cat = agent.get("category") or "Uncategorized"
        if cat not in groups:
            groups[cat] = {"category": cat, "max_score": agent["score"], "agents": []}
        groups[cat]["agents"].append(agent)
        if agent["score"] > groups[cat]["max_score"]:
            groups[cat]["max_score"] = agent["score"]

    sorted_groups = sorted(groups.values(), key=lambda g: g["max_score"], reverse=True)
    return sorted_groups
