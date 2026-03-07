# Agent-Native API Documentation & Composable Tool Design
## Full Research Report for LabLink
### March 5, 2026

---

# Table of Contents

1. [The Shift: Docs Are Now Agent Prompts](#1-the-shift-docs-are-now-agent-prompts)
2. [Progressive Disclosure Architecture](#2-progressive-disclosure-architecture)
3. [The llms.txt Standard](#3-the-llmstxt-standard)
4. [MCP Tool Design Best Practices](#4-mcp-tool-design-best-practices)
5. [Tool Count, Curation & Performance](#5-tool-count-curation--performance)
6. [Documentation Platforms Comparison](#6-documentation-platforms-comparison)
7. [Agent Configuration Standards](#7-agent-configuration-standards)
8. [OpenAPI to MCP Pipeline](#8-openapi-to-mcp-pipeline)
9. [LabLink Implementation Plan](#9-lablink-implementation-plan)
10. [Sources](#10-sources)

---

# 1. The Shift: Docs Are Now Agent Prompts

## 1.1 The Problem with Traditional API Docs

Traditional API documentation was designed for human developers browsing HTML pages. When an AI agent needs to use an API, it faces fundamentally different challenges:

| Challenge | Human Developer | AI Agent |
|-----------|----------------|----------|
| **Discovery** | Browse sidebar, search | Must fit tool index in context window |
| **Comprehension** | Read prose, look at diagrams | Parse structured text, rely on descriptions |
| **Context cost** | Free (eyes are free) | Every token costs money and degrades performance |
| **Error recovery** | Read error page, Google it | Must infer from error response structure |
| **Memory** | Remember across sessions | Fresh context each invocation |

**Key finding:** Scraping a typical API docs HTML site consumes ~500K tokens of messy content. A curated llms.txt delivers the same useful information in ~2-10K tokens -- a **50-250x reduction**.

## 1.2 The New Documentation Consumer Mix

As of 2026, API documentation consumers are:

1. **Human developers** -- Still primary for onboarding, debugging, architecture decisions
2. **LLM coding assistants** -- Claude Code, Cursor, Copilot reading docs to write integration code
3. **AI agents** -- Autonomous systems calling APIs at runtime to accomplish goals
4. **MCP clients** -- LLM tools that discover and invoke APIs through structured protocols

Each audience needs different information at different granularity levels. The solution: **progressive disclosure from a single source of truth**.

## 1.3 Industry Signals

- **Postman** (March 2026): Redesigned entire platform as "AI-native", with Agent Mode and agent-first search workflows
- **Fern** (Feb 2026): Auto-generates llms.txt and llms-full.txt from OpenAPI specs
- **Mintlify**: Ships pages as Markdown to AI agents instead of HTML, reducing token consumption
- **Speakeasy**: MCP server generation from OpenAPI with "tool curation" as a first-class feature
- **Stripe**: Building LLM-powered API design review bots; shifting to "composable primitives" philosophy
- **MCP**: Adopted by Anthropic, OpenAI, Google, Microsoft; donated to Linux Foundation (Jan 2026)

---

# 2. Progressive Disclosure Architecture

## 2.1 The Three-Layer Model

Progressive disclosure for AI agents follows a consistent pattern across every successful implementation (Claude Code Skills, Mintlify, Context7, Honra):

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Layer 1: INDEX (~500 tokens)                       │
│  ─────────────────────────────                      │
│  Tool names + 1-sentence descriptions               │
│  Enough for routing: "Which tool do I need?"         │
│  Loaded automatically at context start               │
│                                                     │
│  Example:                                           │
│  - list_experiments: "List experiments with filters" │
│  - get_instrument_data: "Get parsed data from..."   │
│  - create_experiment: "Register a new experiment"   │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Layer 2: DETAILS (~2-10K tokens per tool)           │
│  ─────────────────────────────────────               │
│  Full parameter schemas, types, constraints          │
│  Loaded on demand when agent selects a tool          │
│                                                     │
│  Example:                                           │
│  create_experiment:                                 │
│    intent: string (required) - What this experiment │
│      aims to achieve                                │
│    parameters: object - Key-value pairs of          │
│      experimental conditions                        │
│    campaign_id: string (optional) - UUID of parent  │
│      optimization campaign                          │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Layer 3: DEEP REFERENCE (10K+ tokens)               │
│  ──────────────────────────────────                  │
│  Code examples, edge cases, error catalog            │
│  Loaded only when agent encounters problems          │
│                                                     │
│  Example:                                           │
│  Full OpenAPI schema, retry strategies, rate limit  │
│  details, webhook payload examples, migration       │
│  guides                                             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## 2.2 Why This Works

**Context rot research:** Models claiming 1M+ token windows experience severe performance degradation at ~100K tokens, with recall drops exceeding 50%. The goal is to keep agent context as lean as possible.

**Token economics:**
- 150 tools with full descriptions = 30,000-60,000 tokens just for metadata
- That's 25-30% of Claude's 200K context before the agent does anything
- Progressive disclosure: ~500 tokens at startup, growing only with what's actually used

**Cognitive load for LLMs:** An agent with 4 well-described tools outperforms one with 40 mediocre ones. Fewer options = more confident, correct tool selection.

## 2.3 Real-World Implementations

### Claude Code Skills
- Startup: Load only skill names + 1-sentence descriptions
- On demand: When user invokes skill, load full SKILL.md
- Deep: Supporting files (API docs, examples) loaded as agent works through tasks
- **Forked contexts**: Complex skills run in isolated sub-agents; only results return

### Context7 (Upstash)
- `resolve-library-id`: Find the right library (Layer 1)
- `get-library-docs(topic, tokens)`: Retrieve specific docs with token limits (Layer 2)
- Backend reranking: Filtering happens server-side, reducing client tokens by 65%
- Average context reduced from ~9.7K to ~3.3K tokens per query

### Mintlify
- All pages served as Markdown to AI agents (not HTML)
- AI Assistant uses agentic retrieval: understands intent, provides contextual answers
- API playground auto-generated from OpenAPI spec

---

# 3. The llms.txt Standard

## 3.1 Overview

Proposed by Jeremy Howard (Answer.AI, September 2024), llms.txt is becoming the de facto standard for making documentation AI-consumable. Think "robots.txt for AI."

**Spec URL:** https://llmstxt.org/

## 3.2 Two File Variants

### llms.txt (Compact Index)
```markdown
# LabLink API

> Lab data integration platform. Connect instruments, parse data, query experiments.

## Core Tools

- [List Experiments](/api/experiments): Query experiments with filters
- [Get Instrument Data](/api/data): Get parsed instrument data for an experiment
- [Create Experiment](/api/experiments/create): Register a new experiment with context
- [Upload Data](/api/upload): Upload instrument output files
- [Search Catalog](/api/search): Semantic search across all lab data
- [Run Analysis](/api/analysis): Trigger analysis on a dataset

## API Reference

- [OpenAPI Spec](/openapi.json): Full machine-readable API specification
- [Authentication](/docs/auth): API key and token authentication
- [Webhooks](/docs/webhooks): Event notification configuration

## SDKs

- [Python SDK](/docs/sdk/python): pip install lablink
- [MCP Server](/docs/mcp): Model Context Protocol integration
```

**Best for:** Large documentation sites. AI reads the summary, identifies relevant sections, follows links for details.

### llms-full.txt (Complete Content)
Contains the **full text** of all documentation pages in a single markdown file. No link traversal needed.

**Best for:** APIs with concise documentation that fits within context windows (~50-100K tokens).

## 3.3 Implementation

Both Fern and Mintlify auto-generate these files from your existing docs. For FastAPI:

1. FastAPI auto-generates OpenAPI spec
2. Mintlify/Fern consumes OpenAPI spec to generate docs site
3. Docs platform auto-generates llms.txt and llms-full.txt
4. AI agents fetch `/llms.txt` first, then drill down as needed

## 3.4 Key Guidelines for LabLink

- **llms.txt**: Keep to ~2K tokens. One sentence per endpoint. Group by workflow, not HTTP method.
- **llms-full.txt**: Include full parameter descriptions, response schemas, error codes. Target ~20-50K tokens.
- **Update automatically**: Both files should regenerate when API changes (CI/CD integration).
- **Include the OpenAPI spec link**: Let agents that prefer raw schemas access them directly.

---

# 4. MCP Tool Design Best Practices

## 4.1 The MCP Standard (2025-2026)

Model Context Protocol (MCP) is now the universal standard for LLM tool integration:
- **Anthropic**: Created MCP, native support in Claude
- **OpenAI**: Adopted MCP for agent tool use
- **Google**: MCP support in Gemini agents
- **Microsoft**: MCP support in Semantic Kernel
- **Linux Foundation**: MCP donated January 2026

MCP provides: tool discovery, context/state handling, semantic feedback, fine-grained security, session history.

## 4.2 Tool Naming Conventions

### DO: Use `verb_noun` in snake_case
```
list_experiments       ✅ Clear action + resource
get_instrument_data    ✅ Specific retrieval
create_experiment      ✅ CRUD-semantic
search_catalog         ✅ Imperative verb
run_analysis           ✅ Action-oriented
```

### DON'T: Use ambiguous or developer-oriented names
```
experiments            ❌ Is this list? create? delete?
data                   ❌ What data? From where?
POST_api_v1_exp        ❌ HTTP method in name
handleExperiment       ❌ CamelCase, vague
```

### Namespace by domain when needed
```
instrument.list_connected     ✅ Domain prefix for disambiguation
experiment.create             ✅ Clear domain
analysis.run_statistical      ✅ Specific operation
```

## 4.3 Tool Description Writing

**Rule 1: Lead with the most important information.**
AI agents may not read the entire description. Put the core purpose in the first clause.

```
✅ "List experiments matching filters. Returns experiment ID, intent, status, and creation date."
❌ "This endpoint allows you to retrieve a list of experiments from the database with various filtering options."
```

**Rule 2: Specify what the tool returns.**
```
✅ "Get parsed instrument data for an experiment. Returns structured JSON with measurements, units, and quality flags."
❌ "Gets data for an experiment."
```

**Rule 3: Include when to use (and when NOT to use).**
```
✅ "Search across all lab data using semantic queries. Use this for natural-language searches. For exact ID lookups, use get_experiment instead."
```

**Rule 4: Note side effects.**
```
✅ "Create a new experiment record. This is a write operation that generates a unique experiment_id."
```

## 4.4 Parameter Description Writing

**Rule 1: Include format, type, and constraints.**
```json
{
  "experiment_id": {
    "type": "string",
    "description": "Unique experiment identifier. UUID format (e.g., 'exp-2026-0305-001'). Required."
  },
  "status": {
    "type": "string",
    "enum": ["planned", "running", "completed", "failed"],
    "description": "Filter by experiment status. Optional, defaults to all statuses."
  },
  "created_after": {
    "type": "string",
    "description": "ISO 8601 datetime. Only return experiments created after this date. Optional."
  }
}
```

**Rule 2: Unambiguous parameter names.**
```
user_id        ✅  (not "user" -- is that a name? an object? an ID?)
instrument_type ✅  (not "type" -- type of what?)
campaign_id    ✅  (not "campaign" -- the ID or the whole object?)
```

## 4.5 Response Schema Design

Every response should follow a consistent envelope:

```json
{
  "data": {
    // The actual result
  },
  "meta": {
    "total_count": 142,
    "page": 1,
    "page_size": 20,
    "has_more": true
  },
  "errors": []
}
```

**Error responses for agents:**
```json
{
  "data": null,
  "errors": [
    {
      "code": "EXPERIMENT_NOT_FOUND",
      "message": "No experiment with ID 'exp-2026-0305-999'",
      "suggestion": "Use list_experiments to find valid experiment IDs",
      "retry": false
    }
  ]
}
```

The `suggestion` field is critical for agents -- it tells them how to recover.

## 4.6 Composable Tool Design Philosophy

Following Stripe's principle: **give agents composable primitives, not rigid frameworks.**

### Atomic Tools (Do One Thing)
```
list_experiments(filters) -> experiment summaries
get_experiment(id) -> full experiment details
create_experiment(context) -> new experiment ID
get_instrument_data(experiment_id) -> parsed data
run_analysis(dataset_id, method) -> analysis results
search_catalog(query) -> search results
```

### NOT Monolithic Tools (Too Much in One)
```
❌ manage_experiment(action, ...) -- "action" param is ambiguous
❌ process_data(input, output, analysis, ...) -- too many responsibilities
```

### Agent Workflow Example
An autonomous lab agent closing the DMTA loop:

```
1. search_catalog("perovskite nanocrystal yield > 70%")
   -> Find relevant past experiments

2. list_experiments(campaign_id="opt-001", status="completed")
   -> Get all experiments in this optimization campaign

3. get_instrument_data(experiment_id="exp-42")
   -> Get HPLC results from best experiment

4. run_analysis(dataset_id="ds-42", method="yield_calculation")
   -> Calculate yield from raw data

5. create_experiment(
     intent="Test 85C based on Bayesian suggestion",
     parameters={temperature: 85, solvent: "ethanol"},
     campaign_id="opt-001",
     predecessor_ids=["exp-42"]
   )
   -> Register next experiment in the loop
```

Each step is a clean, composable primitive. The agent decides the sequence.

---

# 5. Tool Count, Curation & Performance

## 5.1 The Tool Limit Problem

Research findings on tool count vs. agent performance:

| Tool Count | Effect | Source |
|-----------|--------|--------|
| 1-10 | Optimal performance | Industry consensus |
| 10-25 | Good performance, minimal degradation | Anthropic guidance |
| 25-40 | Noticeable accuracy drop | Speakeasy, MCPVerse |
| 40-80 | Significant degradation | Benchmark studies |
| 80+ | Severe: wrong tool selection, hallucinated params | Real-world reports |
| 150 | 30-60K tokens wasted on metadata alone | Kong/MCP analysis |

**Anthropic's guidance:** Tool selection accuracy degrades significantly beyond 30-50 tools.

**MCPVerse benchmark (2025):** Most models exhibited performance degradation as the number of available MCP servers increased.

## 5.2 Toolset Curation Strategy for LabLink

Instead of exposing all endpoints, organize into **curated toolsets by workflow**:

### Toolset: "Lab Data Explorer" (8 tools)
For agents that need to find and understand existing data.
```
list_experiments
get_experiment
get_instrument_data
search_catalog
list_instruments
get_analysis_results
export_data
get_experiment_context
```

### Toolset: "Experiment Planner" (6 tools)
For agents that design and register new experiments.
```
create_experiment
list_campaigns
get_campaign_progress
get_suggestions
record_outcome
link_predecessor
```

### Toolset: "Data Ingestor" (5 tools)
For agents/scripts that upload and process instrument data.
```
upload_file
get_parser_status
list_parsers
trigger_parse
validate_data
```

### Toolset: "Admin" (6 tools)
For configuration and management (rarely needed by science agents).
```
list_users
manage_webhooks
configure_instrument
get_audit_trail
manage_api_keys
get_system_health
```

### Dynamic Toolset Selection
Implement a discovery tool that helps agents self-select:
```
list_toolsets() -> Returns available toolset names + descriptions
get_toolset(name) -> Returns tools for that toolset
```

## 5.3 Server-Side Filtering (Context7 Pattern)

Move filtering from client (expensive LLM tokens) to server:

- Agent sends: `search_catalog("perovskite yield optimization")`
- Server performs: semantic search, reranks, filters to top 5 results
- Agent receives: ~500 tokens of curated results

vs. naive approach:
- Agent receives: 50K tokens of raw results
- Agent uses: expensive LLM reasoning to filter

Context7 reduced average context from ~9.7K to ~3.3K tokens (65% reduction) by doing reranking server-side.

---

# 6. Documentation Platforms Comparison

## 6.1 Platform Matrix

| Platform | AI-Native? | llms.txt | MCP Support | API Playground | OpenAPI | Pricing | Best For |
|----------|-----------|----------|-------------|----------------|---------|---------|----------|
| **Mintlify** | Yes | Yes (auto) | Via integration | Yes (auto from OpenAPI) | 3.0+ | Free-$300/mo | AI-native docs with great DX |
| **Fern** | Yes | Yes (auto) | Via SDK gen | Yes | 3.0+ | Free-custom | SDK + docs generation |
| **ReadMe** | Partial | Manual | No | Yes | 3.0+ | Free-$400/mo | API-first companies |
| **Swagger UI** | No | No | No | Yes | 3.0 | Free | Basic API reference |
| **Redocly** | Partial | No | No | Yes | 3.0+ | Free-$600/mo | Enterprise API docs |
| **Postman** | Yes (v12) | No (but has catalog) | Agent Mode | Yes | 3.0+ | Free-$49/user | API lifecycle management |
| **GitBook** | Partial | No | No | No | No | Free-$13/user | General docs |
| **Docusaurus** | No | Manual | No | Via plugins | Manual | Free | Open-source projects |

## 6.2 Recommendation: Mintlify

For LabLink, **Mintlify** is the strongest choice because:

1. **AI-native by design**: Pages served as Markdown to AI agents (not HTML), reducing tokens
2. **Auto-generated llms.txt**: From your existing docs, no manual maintenance
3. **API playground**: Auto-generated from OpenAPI spec, supports auth testing
4. **AI Assistant**: Agentic retrieval for docs -- users ask questions, get answers with citations
5. **Mintlify Agent**: Monitors codebase, proposes doc updates when you ship changes
6. **Agent analytics**: Track how AI agents consume your docs (new feature 2025)
7. **Good pricing**: Free tier available, $300/mo for Growth
8. **FastAPI-friendly**: Consumes OpenAPI 3.0+ directly

### Alternative: Fern
If you also want auto-generated SDKs (Python, TypeScript), Fern generates both docs AND SDKs from your OpenAPI spec. Now part of Postman. Consider if SDK generation is a priority.

## 6.3 What Mintlify Handles for You

| Task | Manual | With Mintlify |
|------|--------|---------------|
| API reference from OpenAPI | Write HTML manually | Auto-generated |
| llms.txt generation | Write and maintain | Auto-generated |
| Search | Build search engine | Built-in semantic search |
| AI chat over docs | Build RAG pipeline | Built-in AI Assistant |
| Doc updates on code change | Manual review | Mintlify Agent proposes PRs |
| Agent traffic analytics | No visibility | Built-in agent analytics |

---

# 7. Agent Configuration Standards

## 7.1 CLAUDE.md

A simple markdown file at your project root that tells AI coding agents how to work with your codebase. Now stewarded by the Linux Foundation under the Agentic AI Foundation.

**Spec:** https://CLAUDE.md/ | **GitHub:** github.com/agentsmd/CLAUDE.md

**Key sections for LabLink's repo:**
```markdown
# CLAUDE.md

## Project Overview
LabLink is a lab data integration platform. FastAPI backend, React frontend, Go desktop agent.

## Development Environment
- Python 3.12+, FastAPI, PostgreSQL, Redis
- `make dev` to start local environment
- `make test` to run test suite

## API Design Conventions
- All endpoints under /api/v1/
- Tool names: verb_noun snake_case (list_experiments, create_experiment)
- Responses: { data, meta, errors } envelope
- Auth: Bearer token in Authorization header

## MCP Server
- MCP server at src/mcp/server.py
- Tools organized by toolset (explorer, planner, ingestor, admin)
- Tool descriptions must be agent-optimized (lead with purpose, include return type)

## Testing
- pytest for backend: `pytest tests/`
- Tool descriptions tested for clarity: `pytest tests/test_tool_descriptions.py`
```

## 7.2 llms.txt vs. CLAUDE.md vs. MCP

| Standard | Audience | Purpose | Location |
|----------|----------|---------|----------|
| **llms.txt** | AI agents consuming your API | "What can this API do?" | `/llms.txt` on docs site |
| **CLAUDE.md** | AI coding agents working on your code | "How do I develop this codebase?" | Repo root |
| **MCP server** | AI agents using your API at runtime | "How do I call this tool right now?" | Running server |
| **OpenAPI spec** | All audiences | Full technical reference | `/openapi.json` |

All four should exist for LabLink. They serve different purposes and different moments in the agent lifecycle.

---

# 8. OpenAPI to MCP Pipeline

## 8.1 The Pipeline for LabLink

```
FastAPI App (Python)
    │
    ▼ (auto-generated)
OpenAPI 3.1 Spec (openapi.json)
    │
    ├──▶ Mintlify Docs Site
    │       ├── llms.txt (auto)
    │       ├── llms-full.txt (auto)
    │       ├── API Playground (auto)
    │       └── AI Assistant (auto)
    │
    ├──▶ FastMCP Server (Python)
    │       ├── Auto-generated from FastAPI routes
    │       ├── Curated tool descriptions (manually refined)
    │       ├── Organized into toolsets
    │       └── Zod-style input validation
    │
    ├──▶ Python SDK (pip install lablink)
    │       ├── Type-hinted methods
    │       ├── Async support
    │       └── Generated from OpenAPI (Fern or manual)
    │
    └──▶ CLAUDE.md (repo root)
            └── Developer/agent coding instructions
```

## 8.2 FastMCP Integration with FastAPI

FastMCP 2.0+ can auto-generate an MCP server from a FastAPI app:

```python
from fastmcp import FastMCP
from fastapi import FastAPI

app = FastAPI(title="LabLink API")
mcp = FastMCP.from_fastapi(app)

# Auto-generates MCP tools from FastAPI routes
# But then CURATE: override descriptions, group into toolsets
```

**Critical step: Don't ship auto-generated descriptions.** Auto-generation is the starting point. Then:

1. Review each tool description for agent clarity
2. Remove internal/admin endpoints from default toolset
3. Group tools into workflow-based toolsets
4. Add `suggestion` fields to error responses
5. Test with actual LLM agents (Claude, GPT) for accuracy

## 8.3 Tool Description Refinement Example

**Auto-generated (from FastAPI):**
```
Tool: post_api_v1_experiments
Description: Create Api V1 Experiments
```

**Refined for agents:**
```
Tool: create_experiment
Description: Register a new experiment with intent, parameters, and optional campaign link.
  Returns the new experiment_id (UUID). Write operation.
  Required: intent (string describing what the experiment aims to achieve).
  Optional: parameters (object of experimental conditions), campaign_id (UUID),
  predecessor_ids (array of experiment UUIDs this builds on).
```

The refined version gives the agent everything it needs without fetching additional docs.

---

# 9. LabLink Implementation Plan

## 9.1 Phase 1: Foundation (Weeks 1-2 of API work)

### OpenAPI Spec Optimization
- [ ] Ensure every endpoint has a `summary` (1 sentence, agent-friendly)
- [ ] Ensure every endpoint has a `description` (2-3 sentences with return type)
- [ ] Ensure every parameter has `description` with format, type, constraints
- [ ] Add `examples` to all request/response schemas
- [ ] Consistent `operationId` using `verb_noun` pattern
- [ ] Tags organized by workflow domain (not HTTP method)

### Response Envelope
- [ ] Standard `{ data, meta, errors }` wrapper on all endpoints
- [ ] Error responses include `code`, `message`, `suggestion`
- [ ] Pagination via `meta.total_count`, `meta.page`, `meta.has_more`

### CLAUDE.md
- [ ] Create CLAUDE.md at repo root with development instructions

## 9.2 Phase 2: Documentation Site (Week 3)

### Mintlify Setup
- [ ] Initialize Mintlify project pointing at OpenAPI spec
- [ ] Configure auto-generation of API reference
- [ ] Set up llms.txt and llms-full.txt auto-generation
- [ ] Configure AI Assistant
- [ ] Add quickstart guides for:
  - Human developers
  - Python SDK users
  - AI agent integrators

### Content Architecture
```
docs/
├── quickstart/
│   ├── for-developers.md
│   ├── for-CLAUDE.md          # "How to integrate LabLink with your AI agent"
│   └── for-sdk-users.md
├── api-reference/              # Auto-generated from OpenAPI
├── guides/
│   ├── instrument-integration.md
│   ├── experiment-workflows.md
│   └── closed-loop-setup.md
├── mcp/
│   ├── overview.md
│   ├── toolsets.md
│   └── examples.md
└── sdk/
    ├── python.md
    └── examples.md
```

## 9.3 Phase 3: MCP Server (Week 4-5)

### FastMCP Server
- [ ] Auto-generate from FastAPI app
- [ ] Refine all tool descriptions for agent comprehension
- [ ] Organize into 4 toolsets:
  - `explorer` (8 tools): Query and understand data
  - `planner` (6 tools): Design and register experiments
  - `ingestor` (5 tools): Upload and process data
  - `admin` (6 tools): Configuration and management
- [ ] Add discovery tools:
  - `list_toolsets()` -> Available toolset categories
  - `get_toolset(name)` -> Tools in a specific toolset
- [ ] Add Zod-style input validation
- [ ] Test with Claude Code and Claude Desktop

### MCP Server Metadata
```python
mcp = FastMCP(
    name="lablink",
    description="Lab data integration platform. Connect instruments, parse data, query experiments, close the DMTA loop.",
    version="1.0.0"
)
```

## 9.4 Phase 4: Python SDK (Week 6)

### SDK Design
- [ ] `pip install lablink` package
- [ ] Type hints on all methods
- [ ] Async support (`async with LabLink() as client:`)
- [ ] 1:1 mapping with REST API endpoints
- [ ] Rich error objects with suggestions
- [ ] Built-in retry with exponential backoff

### Agent-Friendly SDK Patterns
```python
from lablink import LabLink

client = LabLink(api_key="llk_...")

# Clean, composable primitives
experiments = client.list_experiments(status="completed", campaign_id="opt-001")
data = client.get_instrument_data(experiment_id=experiments[0].id)
result = client.run_analysis(dataset_id=data.dataset_id, method="yield_calculation")

# Close the loop
new_exp = client.create_experiment(
    intent="Test 85C based on optimization suggestion",
    parameters={"temperature_c": 85, "solvent": "ethanol"},
    campaign_id="opt-001",
    predecessor_ids=[experiments[0].id]
)
```

## 9.5 Phase 5: Testing & Analytics (Ongoing)

### Agent Accuracy Testing
- [ ] Automated tests: Give agent a goal, verify it selects correct tools
- [ ] Track tool selection accuracy across Claude, GPT, Gemini
- [ ] A/B test tool descriptions for clarity improvements
- [ ] Monitor Mintlify agent analytics for consumption patterns

### Quality Metrics
| Metric | Target |
|--------|--------|
| Tool selection accuracy | >95% on standard workflows |
| Average tokens per agent interaction | <5K tokens |
| Time to first successful API call (agent) | <30 seconds |
| Error recovery rate (agent finds fix from suggestion) | >80% |
| Developer time to integrate | <30 minutes with SDK |

---

# 10. Sources

## Progressive Disclosure & Agent Architecture
- [Why AI Agents Need Progressive Disclosure, Not More Data](https://www.honra.io/articles/progressive-disclosure-for-ai-agents) - Honra, 2025
- [Progressive Disclosure in AI Agent Skill Design](https://pub.towardsai.net/progressive-disclosure-in-ai-agent-skill-design-b49309b4bc07) - Towards AI, 2025
- [The Coherence Cascade for AI: Progressive Disclosure + Agent Architecture](https://medium.com/@todd.dsm/why-progressive-disclosure-works-for-ai-agents-a-theory-of-motivated-retrieval-665a9d1ea23a) - Medium, Jan 2026
- [Progressive Disclosure: Controlling Context and Tokens in AI Agents](https://medium.com/@martia_es/progressive-disclosure-the-technique-that-helps-control-context-and-tokens-in-ai-agents-8d6108b09289) - Medium, Feb 2026
- [Progressive Disclosure Matters: Applying 90s UX Wisdom to 2026 AI Agents](https://aipositive.substack.com/p/progressive-disclosure-matters) - AI Positive, 2026
- [Progressive Disclosure for Knowledge Discovery in Agentic Workflows](https://medium.com/@prakashkop054/s01-mcp03-progressive-disclosure-for-knowledge-discovery-in-agentic-workflows-8fc0b2840d01) - Medium, 2025

## llms.txt Standard
- [The /llms.txt file specification](https://llmstxt.org/) - Jeremy Howard / Answer.AI, 2024
- [API Docs for AI Agents: llms.txt Guide](https://buildwithfern.com/post/optimizing-api-docs-ai-agents-llms-txt-guide) - Fern, Feb 2026
- [llms.txt and llms-full.txt](https://buildwithfern.com/learn/docs/ai-features/llms-txt) - Fern Documentation
- [Simplifying docs for AI with /llms.txt](https://www.mintlify.com/blog/simplifying-docs-with-llms-txt) - Mintlify
- [llms.txt](https://www.mintlify.com/docs/ai/llmstxt) - Mintlify Docs
- [LLMS.txt 2026 Guide AI Agents & GEO Optimization](https://webscraft.org/blog/llmstxt-povniy-gayd-dlya-vebrozrobnikiv-2026?lang=en) - Webscraft, 2026
- [Give Your AI Agents Deep Understanding With LLMS.txt](https://medium.com/google-cloud/give-your-ai-agents-deep-understanding-with-llms-txt-4f948590332b) - Google Cloud Community
- [Working with llms.txt](https://developer.mastercard.com/platform/documentation/agent-toolkit/working-with-llmstxt/) - Mastercard Developer

## MCP & Tool Design
- [MCP Specification 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26) - Model Context Protocol
- [Tools - Model Context Protocol](https://modelcontextprotocol.io/docs/concepts/tools) - MCP Docs
- [MCP tool descriptions: overview, examples, and best practices](https://www.merge.dev/blog/mcp-tool-description) - Merge, 2025
- [Writing Effective Tools for Agents: Complete MCP Development Guide](https://modelcontextprotocol.info/docs/tutorials/writing-effective-tools/) - MCP Info
- [MCP Server Naming Conventions](https://zazencodes.com/blog/mcp-server-naming-conventions) - Zazen Codes
- [APIs for AI Agents: The 5 Integration Patterns (2026 Guide)](https://composio.dev/blog/apis-ai-agents-integration-patterns) - Composio, 2026
- [API vs. MCP: Everything you need to know](https://composio.dev/blog/api-vs-mcp-everything-you-need-to-know) - Composio
- [MCP Gateways: A Developer's Guide to AI Agent Architecture in 2026](https://composio.dev/blog/mcp-gateways-guide) - Composio, 2026
- [Making REST APIs Agent-Ready: From OpenAPI to MCP Servers](https://arxiv.org/html/2507.16044v1) - arXiv, 2025
- [Exposing OpenAPI as MCP Tools - Semantics Matter](https://blog.christianposta.com/semantics-matter-exposing-openapi-as-mcp-tools/) - Christian Posta

## OpenAPI to MCP Generation
- [Generating MCP tools from OpenAPI: benefits, limits and best practices](https://www.speakeasy.com/mcp/tool-design/generate-mcp-tools-from-openapi) - Speakeasy
- [Advanced tool curation](https://www.speakeasy.com/docs/mcp/build/toolsets/advanced-tool-curation) - Speakeasy
- [Building an MCP server for your FastAPI application](https://www.speakeasy.com/mcp/framework-guides/building-fastapi-server) - Speakeasy
- [OpenAPI to FastMCP](https://gofastmcp.com/integrations/openapi) - FastMCP Docs
- [fastapi-mcp-openapi on PyPI](https://pypi.org/project/fastapi-mcp-openapi/) - PyPI
- [openapi-mcp-codegen](https://github.com/cnoe-io/openapi-mcp-codegen) - GitHub

## Tool Count & Performance
- [How many tools/functions can an AI Agent have?](https://achan2013.medium.com/how-many-tools-functions-can-an-ai-agent-has-21e0a82b7847) - Medium, Feb 2025
- [MCP Overload: Why Your LLM Agent Doesn't Need 20 Tools](https://promptforward.dev/blog/mcp-overload) - PromptForward
- [How to Prevent MCP Tool Overload and Build Faster, Safer AI Agents](https://www.lunar.dev/post/why-is-there-mcp-tool-overload-and-how-to-solve-it-for-your-ai-agents) - Lunar
- [MCPVerse: An Expansive, Real-World Benchmark for Agentic Tool Use](https://arxiv.org/html/2508.16260v1) - arXiv, 2025

## Documentation Platforms
- [Mintlify - The Intelligent Documentation Platform](https://www.mintlify.com/) - Mintlify
- [AI-native documentation](https://www.mintlify.com/docs/ai-native) - Mintlify Docs
- [Mintlify Agent](https://www.mintlify.com/blog/agents-launch) - Mintlify Blog
- [Analytics for AI and agent traffic](https://www.mintlify.com/blog/agent-analytics) - Mintlify Blog
- [Mintlify Review 2026](https://ferndesk.com/blog/mintlify-review) - Ferndesk
- [Fern: SDKs and Docs for your API](https://buildwithfern.com/) - Fern
- [AI features overview](https://buildwithfern.com/learn/docs/ai-features/overview) - Fern Docs
- [The New Postman: AI-Native and Built for the Agentic Era](https://blog.postman.com/new-postman-is-here/) - Postman Blog, 2026
- [Postman Unveils AI-Native API Development](https://www.financialcontent.com/article/bizwire-2026-3-2-postman-unveils-a-new-era-for-ai-native-api-development) - Business Wire, Mar 2026

## Context7
- [Introducing Context7](https://upstash.com/blog/context7-llmtxt-cursor) - Upstash Blog
- [Context7 MCP Integration](https://ef-map.com/blog/context7-mcp-documentation-automation) - EF-Map
- [Context7](https://context7.com/) - Context7

## CLAUDE.md
- [CLAUDE.md specification](https://CLAUDE.md/) - CLAUDE.md
- [CLAUDE.md GitHub](https://github.com/agentsmd/CLAUDE.md) - GitHub
- [How to write a great CLAUDE.md](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/) - GitHub Blog
- [A Complete Guide To CLAUDE.md](https://www.aihero.dev/a-complete-guide-to-agents-md) - AI Hero

## API Design Patterns
- [Stripe & Twilio: Achieving growth through cutting-edge documentation](https://devdocs.work/post/stripe-twilio-achieving-growth-through-cutting-edge-documentation) - DevDocs
- [Cracking the code: how Stripe, Twilio, and GitHub built dev trust](https://business.daily.dev/resources/cracking-the-code-how-stripe-twilio-and-github-built-dev-trust/) - Daily.dev
- [Our recommendations for creating API documentation](https://www.mintlify.com/blog/our-recommendations-for-creating-api-documentation-with-examples) - Mintlify
- [Context Window Management Strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) - Maxim
- [Context engineering in agents](https://docs.langchain.com/oss/python/langchain/context-engineering) - LangChain

---

*Research compiled March 5, 2026. All recommendations based on publicly available sources, documentation, and industry reports.*
