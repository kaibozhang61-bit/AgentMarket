"""
compose_agent MCP tool — combine selected agents into a new composed agent draft.

Given a list of agent IDs and the user's goal:
1. Fetch each agent's public input/output fields from DDB
2. Plan execution order based on field dependencies
3. Generate field mappings between steps
4. Return a composed agent draft for the canvas
"""

from __future__ import annotations

import uuid
from typing import Any

import boto3

from mcp_gateway.config import AWS_REGION, DYNAMODB_TABLE_NAME

_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
_table = _ddb.Table(DYNAMODB_TABLE_NAME)


def compose_agent(
    selected_agents: list[str],
    user_goal: str,
) -> dict[str, Any]:
    """
    Compose a new agent from selected marketplace agents.

    Returns a draft with steps, field mappings, and warnings.
    """
    if not selected_agents:
        return {"error": "No agents selected"}

    # Fetch agent details
    agents = []
    for agent_id in selected_agents:
        resp = _table.get_item(Key={"PK": f"AGENT#{agent_id}", "SK": "LATEST"})
        item = resp.get("Item")
        if not item:
            return {"error": f"Agent '{agent_id}' not found"}
        agents.append(item)

    # Plan execution order — for now, preserve user selection order.
    # Future: topological sort based on field dependencies.
    steps = []
    field_mappings = []
    warnings = []

    for i, agent in enumerate(agents):
        agent_id = agent.get("agentId", "")
        step_id = str(uuid.uuid4())

        # Get public fields only
        public_inputs = _get_public_fields(agent.get("inputSchema", []))
        public_outputs = _get_public_fields(agent.get("outputSchema", []))

        # Build readFromBlackboard references
        read_from: list[str] = []
        if i == 0:
            # First step reads from agent_input
            for field in public_inputs:
                read_from.append(f"agent_input.{field['fieldName']}")
        else:
            # Subsequent steps try to map from previous step outputs
            prev_step_id = steps[i - 1]["stepId"]
            prev_outputs = _get_public_fields(
                agents[i - 1].get("outputSchema", [])
            )
            for field in public_inputs:
                match = _find_field_match(field, prev_outputs)
                if match:
                    read_from.append(
                        f"step_{prev_step_id}_output.{match['fieldName']}"
                    )
                    field_mappings.append({
                        "from_step": prev_step_id,
                        "from_field": match["fieldName"],
                        "to_step": step_id,
                        "to_field": field["fieldName"],
                        "status": "auto_connected"
                        if match["fieldName"] == field["fieldName"]
                        else "llm_suggested",
                    })
                else:
                    # No match — flag as needing transform
                    warnings.append({
                        "step_order": i + 1,
                        "step_id": step_id,
                        "field": field["fieldName"],
                        "message": f"Step {i + 1} needs '{field['fieldName']}' "
                                   f"but no compatible field found in upstream output",
                    })

        step = {
            "stepId": step_id,
            "order": i + 1,
            "type": "agent",
            "agentId": agent_id,
            "outputSchema": public_outputs,
            "readFromBlackboard": read_from,
            "inputMapping": {},
        }
        steps.append(step)

    # Composed agent input = first step's public inputs
    # Composed agent output = last step's public outputs
    composed_input = _get_public_fields(agents[0].get("inputSchema", []))
    composed_output = _get_public_fields(agents[-1].get("outputSchema", []))

    draft = {
        "name": "",
        "description": f"Composed agent for: {user_goal}",
        "steps": steps,
        "inputSchema": composed_input,
        "outputSchema": composed_output,
        "field_mappings": field_mappings,
        "warnings": warnings,
    }

    return {"draft": draft, "step_count": len(steps)}


def _get_public_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to only public-visibility fields."""
    return [
        f for f in fields
        if f.get("visibility", "public") == "public"
    ]


def _find_field_match(
    target: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Find a matching field by exact name or type compatibility.
    Semantic matching (embedding similarity) is deferred to Step 24.
    """
    target_name = target.get("fieldName", "").lower()
    target_type = target.get("type", "")

    # Exact name match
    for c in candidates:
        if c.get("fieldName", "").lower() == target_name:
            return c

    # Same type, similar name substring
    for c in candidates:
        c_name = c.get("fieldName", "").lower()
        if c.get("type") == target_type and (
            target_name in c_name or c_name in target_name
        ):
            return c

    return None
