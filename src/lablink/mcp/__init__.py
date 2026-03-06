"""LabLink MCP server — FastMCP-based tool server for AI agent integration.

Exposes 25 curated tools across 4 toolsets (explorer, planner, ingestor,
admin) plus 2 discovery tools, following the verb_noun naming convention
and the LabLink response envelope pattern.

Run standalone::

    python -m lablink.mcp.server
"""
