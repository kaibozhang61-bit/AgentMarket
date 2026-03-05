"""
MCP Gateway Server — Python MCP server with SSE transport.

Exposes tools: search_agents, run_agent, fetch_run_metadata, compose_agent

Usage:
    python -m mcp_gateway.server
    # or
    uvicorn mcp_gateway.server:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from mcp_gateway.tools.compose import compose_agent
from mcp_gateway.tools.metadata import fetch_run_metadata
from mcp_gateway.tools.run import run_agent
from mcp_gateway.tools.search import search_agents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = Server("agent-marketplace-gateway")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_agents",
            description=(
                "Search for agents in the marketplace. "
                "Always call this after clarifying user intent. "
                "Never call run_agent without explicit user confirmation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Natural language description of the task",
                    },
                    "available_inputs": {
                        "type": "string",
                        "description": "What data the user can provide (optional)",
                    },
                    "desired_outputs": {
                        "type": "string",
                        "description": "What results the user wants (optional)",
                    },
                },
                "required": ["task_description"],
            },
        ),
        Tool(
            name="run_agent",
            description=(
                "Execute a published agent. Only call after the user explicitly "
                "confirms they want to run the agent. Show a confirmation summary "
                "with inputs before calling."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the agent to execute",
                    },
                    "input_data": {
                        "type": "object",
                        "description": "Input data matching the agent's inputSchema",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "ID of the user triggering the run",
                    },
                },
                "required": ["agent_id", "input_data", "user_id"],
            },
        ),
        Tool(
            name="fetch_run_metadata",
            description=(
                "Fetch historical run metadata for one or more agents. "
                "Used for metrics analysis and agent comparison."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of agent IDs to fetch run history for",
                    },
                    "last_n": {
                        "type": "integer",
                        "description": "Number of recent runs to fetch per agent (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["agent_ids"],
            },
        ),
        Tool(
            name="compose_agent",
            description=(
                "Given a list of user-selected agents, plan execution order, "
                "field mappings, and generate a composed agent draft for the canvas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "selected_agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of selected agent IDs",
                    },
                    "user_goal": {
                        "type": "string",
                        "description": "User's original goal",
                    },
                },
                "required": ["selected_agents", "user_goal"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "search_agents":
            result = search_agents(
                task_description=arguments["task_description"],
                available_inputs=arguments.get("available_inputs", ""),
                desired_outputs=arguments.get("desired_outputs", ""),
            )
        elif name == "run_agent":
            result = run_agent(
                agent_id=arguments["agent_id"],
                input_data=arguments["input_data"],
                user_id=arguments["user_id"],
            )
        elif name == "fetch_run_metadata":
            result = fetch_run_metadata(
                agent_ids=arguments["agent_ids"],
                last_n=arguments.get("last_n", 100),
            )
        elif name == "compose_agent":
            result = compose_agent(
                selected_agents=arguments["selected_agents"],
                user_goal=arguments["user_goal"],
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, default=str))]


# ── SSE Transport (Starlette app) ────────────────────────────────────────────

sse = SseServerTransport("/messages/")


async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp.run(
            streams[0],
            streams[1],
            mcp.create_initialization_options(),
        )


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
