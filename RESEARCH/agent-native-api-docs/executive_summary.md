# Agent-Native API Documentation & Tool Design: Executive Summary
## Making LabLink's API Top-Tier for AI Agent Interactivity
### Research Date: March 5, 2026

---

## The Core Insight

**The API spec is no longer just developer documentation -- it's the agent's brain.** When an LLM agent uses your API, the tool descriptions, parameter names, and response schemas ARE the prompt that determines whether the agent succeeds or fails. A well-designed API doc surface is the difference between an agent that flawlessly orchestrates lab experiments and one that hallucinates instrument IDs.

## The Three-Layer Documentation Architecture

The emerging best practice is a **progressive disclosure** architecture that serves three audiences from the same source of truth:

```
Layer 1: DISCOVERY (costs ~500 tokens)
├── llms.txt -- 1-sentence per tool, links to details
├── Tool name + description index
└── "What can this API do?" for routing decisions

Layer 2: OPERATIONAL (costs ~2-10K tokens per tool)
├── llms-full.txt -- Complete docs in markdown
├── Full parameter descriptions with types, constraints, examples
└── "How do I use this specific tool?" for execution

Layer 3: DEEP REFERENCE (costs 10K+ tokens, loaded on demand)
├── OpenAPI spec (full JSON schema)
├── Code examples, edge cases, error catalogs
└── "What are all the edge cases?" for complex operations
```

This mirrors how Claude Code's Skill system works: load only names at startup, fetch full content on demand.

## Five Non-Negotiable Practices for LabLink

### 1. Publish `/llms.txt` and `/llms-full.txt`
The emerging standard (Jeremy Howard/Answer.AI, adopted by Fern, Mintlify, Mastercard). A markdown file at your docs root that AI agents fetch before anything else. Reduces token consumption by 90%+ vs. crawling HTML.

### 2. Cap Exposed Tools at 15-25 Per Context
Research shows LLM performance degrades significantly beyond 30-40 tools. 150 tools = 30-60K wasted tokens just on metadata. LabLink should organize tools into **curated toolsets** by workflow, not dump every endpoint.

### 3. Write Tool Descriptions for Agents, Not Developers
Tool descriptions are the #1 factor in agent accuracy. Lead with the most important info. Use imperative verbs (`get_`, `list_`, `create_`). Include format hints in parameter descriptions ("UUID format", "ISO 8601 datetime").

### 4. Build an MCP Server (Not Just REST)
MCP is now the universal standard (adopted by Anthropic, OpenAI, Google, Microsoft; donated to Linux Foundation Jan 2026). FastMCP can auto-generate from your FastAPI app. But **curate** -- don't auto-expose every endpoint.

### 5. Use Progressive Disclosure in the MCP Server Itself
Don't load all tools at startup. Use a discovery pattern:
- `list_capabilities()` -- returns available tool categories
- `get_tools(category)` -- returns tools for a specific workflow
- `get_tool_details(tool_name)` -- returns full schema + examples

## Recommended Documentation Stack for LabLink

| Layer | Tool | Purpose |
|-------|------|---------|
| **Docs site** | Mintlify | Searchable, AI-native, auto-generates llms.txt, API playground from OpenAPI |
| **API spec** | OpenAPI 3.1 (auto-generated from FastAPI) | Single source of truth |
| **MCP server** | FastMCP (Python) | Agent integration layer, auto-generated from FastAPI then curated |
| **SDK** | Fern or manual | `pip install lablink` with type hints |
| **Agent config** | CLAUDE.md | Project-level agent instructions |
| **Discovery** | llms.txt + llms-full.txt | Progressive disclosure for LLM consumption |

## What "Top-Tier" Looks Like

| Dimension | Mediocre | Top-Tier (LabLink Target) |
|-----------|----------|--------------------------|
| **Documentation** | OpenAPI JSON dump | Progressive disclosure: llms.txt -> llms-full.txt -> full spec |
| **Tool count** | 80+ endpoints as flat list | 15-25 curated tools organized by workflow |
| **Descriptions** | Dev-oriented ("POST /api/experiments") | Agent-oriented ("Create a new experiment with parameters and link to campaign") |
| **Naming** | Inconsistent (mix of styles) | `verb_noun` snake_case, CRUD-semantic (`list_experiments`, `create_experiment`) |
| **Responses** | Varied formats | Consistent JSON with `data`, `meta`, `errors` envelope |
| **Errors** | HTTP status + generic message | Structured errors with `code`, `message`, `suggestion`, `retry_after` |
| **Discovery** | None (read the docs) | `list_capabilities()` -> `get_tools(category)` -> execute |
| **Examples** | Separate docs page | Inline in tool descriptions and parameter schemas |

## Cost of NOT Doing This

Without agent-native documentation:
- AI agents will misuse your API (wrong parameters, missing required fields)
- Agents will consume 10-100x more tokens per interaction (crawling HTML docs)
- Integration with Claude, GPT, and other LLM agents will require custom wrappers
- You lose the "works with AI agents out of the box" competitive advantage

---

*Full report: `full_report.md` | Implementation guide: `research_notes/implementation_guide.md`*
