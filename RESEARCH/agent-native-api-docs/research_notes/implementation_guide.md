# LabLink Agent-Native API: Implementation Guide

## Quick Reference: What to Build and in What Order

### Week 1-2: OpenAPI Spec Hardening

**Goal:** Make your FastAPI-generated OpenAPI spec agent-grade.

#### Endpoint Naming Convention
```python
# In FastAPI, use operation_id for clean tool names
@app.get("/api/v1/experiments", operation_id="list_experiments")
@app.get("/api/v1/experiments/{id}", operation_id="get_experiment")
@app.post("/api/v1/experiments", operation_id="create_experiment")
@app.get("/api/v1/data/{experiment_id}", operation_id="get_instrument_data")
@app.post("/api/v1/analysis/run", operation_id="run_analysis")
@app.post("/api/v1/search", operation_id="search_catalog")
```

#### Description Template for Every Endpoint
```python
@app.get(
    "/api/v1/experiments",
    operation_id="list_experiments",
    summary="List experiments matching filters",  # 1 sentence, for llms.txt
    description=(
        "List experiments matching filters. Returns experiment summaries with ID, "
        "intent, status, creation date, and instrument types. "
        "Supports filtering by status, campaign, date range, and instrument type. "
        "Results are paginated (default 20 per page). "
        "Use get_experiment for full details on a specific experiment."
    ),
    tags=["explorer"]  # Toolset grouping
)
```

#### Parameter Description Template
```python
class ExperimentFilters(BaseModel):
    status: Optional[str] = Field(
        None,
        description="Filter by status. One of: planned, running, completed, failed. Optional.",
        json_schema_extra={"examples": ["completed"]}
    )
    campaign_id: Optional[str] = Field(
        None,
        description="UUID of optimization campaign. Only return experiments in this campaign. Optional.",
        json_schema_extra={"examples": ["camp-2026-001"]}
    )
    created_after: Optional[str] = Field(
        None,
        description="ISO 8601 datetime. Only experiments created after this date. Optional.",
        json_schema_extra={"examples": ["2026-03-01T00:00:00Z"]}
    )
    instrument_type: Optional[str] = Field(
        None,
        description="Filter by instrument type (e.g., 'hplc', 'pcr', 'plate_reader'). Optional."
    )
    page: int = Field(1, description="Page number for pagination. Starts at 1.", ge=1)
    page_size: int = Field(20, description="Results per page. Default 20, max 100.", ge=1, le=100)
```

#### Standard Response Envelope
```python
class APIResponse(BaseModel, Generic[T]):
    data: Optional[T] = None
    meta: Optional[PaginationMeta] = None
    errors: List[APIError] = []

class APIError(BaseModel):
    code: str  # Machine-readable: "EXPERIMENT_NOT_FOUND"
    message: str  # Human-readable: "No experiment with ID 'exp-999'"
    suggestion: Optional[str] = None  # Agent-actionable: "Use list_experiments to find valid IDs"
    retry: bool = False  # Should agent retry?
    retry_after: Optional[int] = None  # Seconds to wait if retry=True

class PaginationMeta(BaseModel):
    total_count: int
    page: int
    page_size: int
    has_more: bool
```

### Week 3: Mintlify Setup

#### 1. Initialize Mintlify
```bash
npx mintlify init
```

#### 2. Configure mint.json
```json
{
  "name": "LabLink",
  "openapi": "openapi.json",
  "ai": {
    "llmstxt": true,
    "assistant": true
  },
  "navigation": [
    {
      "group": "Getting Started",
      "pages": ["quickstart/for-developers", "quickstart/for-agents", "quickstart/for-sdk"]
    },
    {
      "group": "API Reference",
      "pages": ["api-reference/explorer", "api-reference/planner", "api-reference/ingestor"]
    },
    {
      "group": "MCP Integration",
      "pages": ["mcp/overview", "mcp/toolsets", "mcp/examples"]
    }
  ]
}
```

#### 3. Create "For Agents" Quickstart
```markdown
# Integrating LabLink with AI Agents

## MCP Server (Recommended)
The fastest way to connect an AI agent to LabLink.

### Claude Desktop / Claude Code
Add to your MCP config:
{
  "mcpServers": {
    "lablink": {
      "command": "lablink-mcp",
      "args": ["--api-key", "YOUR_API_KEY"]
    }
  }
}

### Available Toolsets
- **explorer**: Query and understand existing lab data (8 tools)
- **planner**: Design and register new experiments (6 tools)
- **ingestor**: Upload and process instrument data (5 tools)

## REST API
Full OpenAPI spec: /openapi.json

## Python SDK
pip install lablink

## llms.txt
Machine-readable API index: /llms.txt
Full documentation: /llms-full.txt
```

### Week 4-5: MCP Server

#### FastMCP Server Structure
```python
# src/mcp/server.py
from fastmcp import FastMCP

mcp = FastMCP(
    name="lablink",
    description="Lab data integration platform for autonomous labs. "
                "Query experiments, parse instrument data, close the DMTA loop."
)

# === DISCOVERY TOOLS ===

@mcp.tool()
def list_toolsets() -> dict:
    """List available tool categories. Returns toolset names and descriptions.
    Use this first to discover what LabLink can do."""
    return {
        "toolsets": [
            {"name": "explorer", "description": "Query and analyze existing lab data", "tool_count": 8},
            {"name": "planner", "description": "Design and register experiments", "tool_count": 6},
            {"name": "ingestor", "description": "Upload and process instrument files", "tool_count": 5},
        ]
    }

@mcp.tool()
def get_toolset(name: str) -> dict:
    """Get tools available in a specific toolset.
    Args:
        name: Toolset name from list_toolsets (e.g., 'explorer', 'planner', 'ingestor')
    Returns tool names and descriptions for the requested toolset."""
    # Return tool index for the requested toolset
    ...

# === EXPLORER TOOLSET ===

@mcp.tool()
def list_experiments(
    status: str | None = None,
    campaign_id: str | None = None,
    created_after: str | None = None,
    instrument_type: str | None = None,
    page: int = 1,
    page_size: int = 20
) -> dict:
    """List experiments matching filters. Returns summaries with ID, intent, status, date.
    For full experiment details, use get_experiment with the experiment_id.
    Args:
        status: One of 'planned', 'running', 'completed', 'failed'. Optional.
        campaign_id: UUID of optimization campaign. Optional.
        created_after: ISO 8601 datetime (e.g., '2026-03-01T00:00:00Z'). Optional.
        instrument_type: e.g., 'hplc', 'pcr', 'plate_reader'. Optional.
        page: Page number, starts at 1.
        page_size: Results per page, default 20, max 100.
    """
    ...

@mcp.tool()
def search_catalog(
    query: str,
    max_results: int = 5
) -> dict:
    """Search across all lab data using natural language. Returns ranked results.
    Use for finding experiments by topic, chemical, or outcome.
    For exact ID lookups, use get_experiment instead.
    Args:
        query: Natural language search (e.g., 'perovskite yield optimization above 70%')
        max_results: Max results to return, default 5. Server handles reranking.
    """
    ...
```

#### Key Implementation Details

1. **Discovery-first pattern**: `list_toolsets()` and `get_toolset()` let agents self-select relevant tools
2. **Server-side filtering**: `search_catalog` does reranking on server, returns only top results
3. **Cross-references in descriptions**: "For full details, use get_experiment" helps agents chain tools
4. **Format hints in args**: "ISO 8601 datetime (e.g., '2026-03-01T00:00:00Z')"

### Week 6: Python SDK

```python
# lablink/client.py
from typing import Optional, List
from lablink.models import Experiment, InstrumentData, AnalysisResult

class LabLink:
    """LabLink Python SDK. Connect to the lab data integration platform."""

    def __init__(self, api_key: str, base_url: str = "https://api.lablink.io"):
        ...

    # Explorer tools
    def list_experiments(
        self,
        status: Optional[str] = None,
        campaign_id: Optional[str] = None,
        created_after: Optional[str] = None,
        instrument_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> List[Experiment]:
        """List experiments matching filters."""
        ...

    def get_experiment(self, experiment_id: str) -> Experiment:
        """Get full details for a specific experiment."""
        ...

    def get_instrument_data(self, experiment_id: str) -> InstrumentData:
        """Get parsed instrument data for an experiment."""
        ...

    def search_catalog(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Semantic search across all lab data."""
        ...

    # Planner tools
    def create_experiment(
        self,
        intent: str,
        parameters: Optional[dict] = None,
        campaign_id: Optional[str] = None,
        predecessor_ids: Optional[List[str]] = None
    ) -> Experiment:
        """Register a new experiment with context."""
        ...

    # Analysis tools
    def run_analysis(
        self,
        dataset_id: str,
        method: str,
        config: Optional[dict] = None
    ) -> AnalysisResult:
        """Run analysis on a dataset. Returns structured results."""
        ...
```

## Testing Agent Comprehension

### Tool Description Quality Tests
```python
# tests/test_tool_descriptions.py

def test_tool_descriptions_lead_with_action():
    """Every tool description starts with an imperative verb."""
    for tool in mcp.tools:
        first_word = tool.description.split()[0]
        assert first_word.endswith(('s', 'e', 'd', 'n', 't', 'r', 'y')), \
            f"Tool '{tool.name}' description doesn't start with action verb: '{first_word}'"

def test_tool_descriptions_mention_return_type():
    """Every tool description mentions what it returns."""
    for tool in mcp.tools:
        assert any(word in tool.description.lower() for word in ['returns', 'returns:', 'result']), \
            f"Tool '{tool.name}' doesn't describe return value"

def test_tool_names_are_verb_noun():
    """Every tool name follows verb_noun pattern."""
    for tool in mcp.tools:
        parts = tool.name.split('_')
        assert len(parts) >= 2, f"Tool '{tool.name}' should be verb_noun"

def test_parameter_descriptions_include_format():
    """ID and date parameters include format hints."""
    for tool in mcp.tools:
        for param in tool.parameters:
            if param.name.endswith('_id'):
                assert 'uuid' in param.description.lower() or 'format' in param.description.lower(), \
                    f"Parameter '{param.name}' in '{tool.name}' missing format hint"

def test_tool_count_per_toolset():
    """No toolset exceeds 25 tools."""
    for toolset in TOOLSETS:
        assert len(toolset.tools) <= 25, \
            f"Toolset '{toolset.name}' has {len(toolset.tools)} tools (max 25)"
```

### Agent Integration Tests
```python
# tests/test_agent_accuracy.py
import anthropic

def test_agent_finds_experiments():
    """Agent correctly selects list_experiments when asked to find data."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        tools=mcp.get_tool_schemas(),
        messages=[{"role": "user", "content": "Find all completed HPLC experiments from this week"}]
    )
    tool_use = response.content[0]
    assert tool_use.name == "list_experiments"
    assert tool_use.input["status"] == "completed"
    assert tool_use.input["instrument_type"] == "hplc"

def test_agent_uses_search_for_natural_language():
    """Agent correctly selects search_catalog for open-ended queries."""
    # ...

def test_agent_chains_tools_correctly():
    """Agent chains list_experiments -> get_instrument_data -> run_analysis."""
    # ...
```

## Checklist Summary

### P0 (Ship with API)
- [ ] `operation_id` on all FastAPI endpoints (verb_noun pattern)
- [ ] `summary` on all endpoints (1 sentence, agent-friendly)
- [ ] `description` with format hints on all parameters
- [ ] `{ data, meta, errors }` response envelope with `suggestion` in errors
- [ ] CLAUDE.md at repo root

### P1 (Ship with docs site)
- [ ] Mintlify configured with OpenAPI auto-import
- [ ] llms.txt auto-generating
- [ ] llms-full.txt auto-generating
- [ ] "For Agents" quickstart page

### P2 (Ship with agent integration)
- [ ] FastMCP server with curated toolsets
- [ ] `list_toolsets()` / `get_toolset()` discovery pattern
- [ ] Server-side filtering on search tools
- [ ] Python SDK (`pip install lablink`)
- [ ] Agent accuracy tests
- [ ] Tool description quality tests
