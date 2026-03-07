# Research: Agent-Native API Documentation & Tool Design for LabLink

**Date:** March 5, 2026
**Purpose:** Ensure LabLink's API and documentation are top-tier for AI agent interactivity

## Files

| File | Description |
|------|-------------|
| `executive_summary.md` | Key findings: progressive disclosure, tool curation, recommended stack |
| `full_report.md` | Complete 10-section report with 80+ sources |
| `research_notes/implementation_guide.md` | Code-level guide: FastAPI patterns, MCP server, SDK, testing |

## Key Decisions

1. **Docs platform:** Mintlify (AI-native, auto llms.txt, API playground)
2. **MCP server:** FastMCP auto-generated from FastAPI, then curated into toolsets
3. **Tool organization:** 4 curated toolsets (explorer/planner/ingestor/admin), max 25 tools each
4. **Discovery pattern:** `list_toolsets()` -> `get_toolset(name)` -> execute tool
5. **Standards:** llms.txt + CLAUDE.md + MCP + OpenAPI 3.1
