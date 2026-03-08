# Quality Score

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Domain quality grades and known gaps. Updated when significant domain work happens.

## Grading Scale

- **A** — Well-tested, documented, no known issues
- **B** — Mostly solid, minor gaps
- **C** — Works but needs attention
- **D** — Significant technical debt or gaps
- **F** — Actively problematic

## Domain Grades

| Domain | Grade | Notes |
|---|---|---|
| Core / Business Logic (services) | B | 10 services, good coverage; experiment state machine needs more edge-case tests |
| API / Routing (routers) | B | 13 routers, all follow thin-router pattern; admin router needs rate limiting |
| Authentication | B | JWT + bcrypt, org scoping enforced; no refresh token rotation yet |
| Instrument Parsers | B | 5 parsers with 24 fixture files; allotropy fallback added in week 5-6 |
| MCP Server | B | 25 tools, 4 toolsets; planner/ingestor/admin toolsets partially stubbed in backend/app |
| Data Layer (models) | A | 16 ORM models, proper mixins, soft delete, hash-chained audit trail |
| Schemas | A | Pydantic v2, Envelope[T] pattern consistent, Field descriptions as API docs |
| Tasks (Celery) | B | Parse/webhook/index pipeline complete; sync fallback works; needs retry tests |
| Frontend | C | Functional SPA; needs more component tests; Plotly charts need agent-readable JSON |
| Desktop Agent (Go) | C | File watcher implemented; needs integration tests; no retry queue yet |
| Tests | A | 1,296 tests, asyncio_mode=auto, fixture-based parser tests, no Docker needed |

## Known Gaps

- Frontend: charts don't yet return machine-readable JSON alongside visualizations (agent parity gap)
- Desktop agent: no persistent retry queue for failed uploads (in-memory only)
- MCP planner/ingestor/admin toolsets partially implemented in `backend/app/` but not yet in `src/lablink/mcp/`
- No refresh token rotation (access tokens have short TTL, but refresh tokens are long-lived)
- Admin router lacks rate limiting for sensitive operations

## Improvement Tracker

See [docs/execution-plans/](./execution-plans/) for active plans targeting these gaps.
