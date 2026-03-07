# mcp Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the FastMCP server.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

FastMCP 3.0 server exposing 25 tools across 4 toolsets (Explorer, Planner, Ingestor, Admin) plus 2 discovery tools (`list_toolsets`, `get_toolset`). Runs as a standalone process: `python -m lablink.mcp.server`. AI agents use these tools to interact with LabLink programmatically.

## Coding Conventions

- Tool names follow `verb_noun` snake_case: `list_experiments`, `create_upload`, `get_instrument_data`.
- Every tool parameter must have a `description` — it's injected directly into the agent's context.
- Tools must return structured data matching the `Envelope[T]` shape where possible.
- Tool implementations call the same REST services (or service functions directly) — no duplicated logic.
- Group tools into toolsets for progressive disclosure: agents call `list_toolsets` first, then `get_toolset` to get the tools for a domain.

## Patterns

- **Progressive disclosure**: Agents call `list_toolsets` first, then `get_toolset("<name>")` to get specific tools. Never expose all 25 tools at once.
- **`@mcp.tool()` decorator**: All tools registered this way. Name = operation_id, docstring = agent-visible description.
- **Service passthrough**: Tools are thin wrappers — call service functions directly, return structured data. No business logic inline.
- **Shared auth context**: Tools receive an org/user context injected via MCP session, same as REST `Depends(get_current_org)`.

## Toolset Map

| Toolset | Tools | Purpose |
|---|---|---|
| explorer | 8 | Read/search: list_experiments, get_experiment, get_instrument_data, search_catalog, list_instruments, list_uploads, get_chart_data, create_export |
| planner | 7 | Write/plan: create_experiment, update_experiment, record_outcome, link_upload_to_experiment, create_campaign, get_campaign_progress, list_campaigns |
| ingestor | 4 | Upload: create_upload, list_parsers, get_upload, reparse_upload |
| admin | 4 | Admin: get_usage_stats, list_agents, create_webhook, list_audit_events |
| discovery | 2 | Meta: list_toolsets, get_toolset |

## What Belongs Here

- FastMCP tool definitions (`@mcp.tool()` decorated functions).
- Toolset metadata (descriptions, tool lists) for the discovery tools.
- The `server.py` entry point and MCP app configuration.
- `__main__.py` for `python -m lablink.mcp.server`.

## What Doesn't Belong Here

- Business logic — call `services/` directly or via REST.
- Database queries — go through services.
- Duplicated logic from routers — MCP tools and REST endpoints should share service-layer code.

## Key Dependencies

- `fastmcp` 3.0+
- `lablink.services.*` (tools call services directly for efficiency)
- `lablink.schemas.*` (response shaping)
- `lablink.dependencies` (get_db, auth — adapted for MCP context)

## Testing Approach

Test tools by calling service functions directly in unit tests. End-to-end MCP tool tests (using an MCP test client) are planned — see `docs/QUALITY_SCORE.md` for current gap. For now, rely on service-layer tests for coverage.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
