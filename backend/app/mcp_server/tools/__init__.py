"""MCP toolsets for LabLink.

Four toolsets + 2 discovery tools = 25 total tools:
- explorer: 8 tools for browsing data
- planner: 7 tools for pipeline planning
- ingestor: 4 tools for data ingestion
- admin: 4 tools for administration
- discovery: 2 tools (list_toolsets, get_tool_help)
"""

from app.mcp_server.tools.explorer import EXPLORER_TOOLS

__all__ = [
    "EXPLORER_TOOLS",
]
