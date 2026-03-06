"""MCP Server for LabLink — agent-native lab data integration.

Provides a FastMCP server with 25 curated tools (10 live + 15 stub slots):
  - discovery (2): list_toolsets, get_tool_help
  - explorer (8): search_files, list_experiments, get_file_metadata,
                   get_experiment_detail, list_datasets, get_parse_result,
                   list_instruments, get_dataset_summary
  - planner (7): stub
  - ingestor (4): stub
  - admin (4): stub
"""

from app.mcp_server.context import MCPContext
from app.mcp_server.server import create_mcp_server

__all__ = [
    "MCPContext",
    "create_mcp_server",
]
