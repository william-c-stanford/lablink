# mcp_server Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `mcp_server` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

FastMCP server for the `backend/app` alternative structure. Provides agent-accessible tools for exploring lab data. The primary MCP server is in `src/lablink/mcp/` — this module is the alternative scaffold version with a partial implementation of the explorer toolset.

**Note**: `backend/app/` is an alternative structure from the initial Ouroboros scaffold. Both coexist.

## Architecture Within This Module

- `server.py` — FastMCP server instantiation, toolset registry, `list_toolsets` and `get_tool_help` discovery tools
- `context.py` — `MCPContext` dataclass carrying db session, org, and user for tool calls
- `types.py` — Type aliases for MCP tool return types
- `tools/` — Tool handler functions organized by toolset (`explorer/`, etc.)

## Coding Conventions

- All tool names use `verb_noun` snake_case: `search_files`, `list_experiments`, `get_file_metadata`
- Every tool response includes a `suggestion` field for agent recovery
- Tool docstrings are the MCP tool descriptions — make them precise and agent-readable
- Tools are organized into toolsets: `discovery`, `explorer`, `planner`, `ingestor`, `admin`

## Patterns

**Toolset registry**: `TOOLSET_DESCRIPTIONS` maps toolset name → description. `_TOOL_TOOLSET_MAP` maps tool name → toolset name. Both are populated at registration time.

**Tool registration**: Tools are registered via `register_toolset_tools(mcp, toolset_name, tools_list)` which wraps each handler (sync or async) with the FastMCP decorator pattern.

**Discovery tools**: `list_toolsets` and `get_tool_help` are always available — they let agents discover what tools exist before calling them.

## Key Types and Interfaces

- `MCPContext` (`context.py`) — `db`, `organization_id`, `user_id` per request
- `TOOLSET_DESCRIPTIONS` (`server.py`) — `dict[str, str]` of toolset metadata
- `EXPLORER_TOOLS` (`tools/explorer/`) — list of (name, handler) tuples for the explorer toolset

## What Belongs Here

- FastMCP server setup and toolset registration
- MCP tool handler functions
- Context and type definitions for MCP tools

## What Does Not Belong Here

- Business logic (call services from `backend/app/services/`)
- HTTP routing (that's in `backend/app/routers/`)

## Key Dependencies

- `fastmcp` — MCP server framework
- `app.mcp_server.context.MCPContext` — per-request context
- `app.services.*` — delegate to services for data access

## Testing Approach

MCP tools are tested by calling handler functions directly with a mock `MCPContext`. Verify that tools return proper `suggestion` fields on error paths.

## Common Gotchas

- This is the `backend/app` version. The primary MCP server is `src/lablink/mcp/server.py`.
- Tool names must be globally unique across toolsets — duplicates cause registration conflicts.
- FastMCP wraps both sync and async handlers — the `inspect.iscoroutinefunction()` check in `server.py` handles this.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
