# Quality Score

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

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
| Core / Business Logic (services) | B | 10 services, good coverage; export_service minimal |
| API / Routing | A | 13 routers, thin, envelope pattern consistent |
| Parsers | B | 5 parsers with fixture tests; allotropy fallback integrated |
| Authentication | B | JWT + API tokens; role enforcement consistent |
| Data Layer (models) | A | 16 models, SQLAlchemy 2.0, hash-chained audit trail |
| MCP Server | B | 25 tools across 4 toolsets; needs end-to-end agent tests |
| Frontend | C | React SPA exists; needs more component tests |
| Desktop Agent (Go) | C | File watch + upload works; limited test coverage |
| Tests | A | 1,296 tests passing, asyncio_mode=auto, no Docker needed |

## Known Gaps

- `export_service.py` — minimal implementation; needs CSV/Excel export formats
- Frontend component tests — Vitest setup exists but coverage is low
- Go agent (`agent/`) — integration tests against mock API missing
- E2E agent tests for MCP toolsets — need a test harness
- Elasticsearch search quality — basic tokenization, no field boosting yet

## Improvement Tracker

See `plans/lablink-product-roadmap.md` for the prioritized improvement backlog.
