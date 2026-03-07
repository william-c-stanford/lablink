# Architecture — LabLink

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Top-level map of domains and package layering.
> Update this when you add or remove major modules or change how they relate.

## Stack

- **Backend**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Celery + Redis / PostgreSQL / Elasticsearch / S3
- **Frontend**: React + TypeScript + Tailwind + Plotly.js + Vite
- **Desktop Agent**: Go 1.22+ (fsnotify + BBolt) — watches local instrument directories
- **MCP Server**: FastMCP 3.0+ — 25 tools across 4 toolsets
- **Dev mode**: SQLite + aiosqlite, local filesystem, in-memory search, sync task fallback (no Docker needed)

## Domain Map

```
Ingestion  →  Parsing  →  Storage  →  Search  →  API  →  MCP / Frontend
  (uploads)    (parsers)   (PG + S3)   (ES)     (REST)   (agents / UI)
```

- **Ingestor**: File uploads arrive via REST (`/uploads`) or desktop agent file-watch
- **Parsers**: Instrument-specific parsers produce a canonical `ParsedResult` (ASM-compatible)
- **Storage**: PostgreSQL is source of truth; S3 stores raw files; ES is eventually consistent
- **Experiments / Campaigns**: Group uploads into reproducible experiment runs and multi-step campaigns
- **MCP Server**: 25 tools expose every read/write operation to AI agents
- **Audit Trail**: Append-only, hash-chained events — never deleted

## Package / Directory Layout

```
lablink/
  src/lablink/       # Primary Python package
    config.py        # Pydantic-settings (LABLINK_ env prefix)
    database.py      # Async SQLAlchemy engine + session factory
    main.py          # FastAPI app factory
    dependencies.py  # get_db, get_current_user, get_current_org, require_role
    exceptions.py    # LabLinkError hierarchy
    models/          # 16 SQLAlchemy ORM models
    schemas/         # Pydantic v2 request/response + envelope
    routers/         # 13 thin FastAPI routers
    services/        # 10 business-logic services (no HTTP awareness)
    parsers/         # 5 instrument parsers + BaseParser ABC + registry
    tasks/           # Celery tasks (parse, webhook, index) with sync fallback
    mcp/             # FastMCP server (25 tools)
  backend/app/       # Alternative structure from initial scaffold (coexists)
  frontend/          # React + TypeScript + Vite SPA
  agent/             # Go desktop agent (file-watch → upload)
  tests/             # 56 test files, asyncio_mode=auto
  migrations/        # Alembic migrations
```

## Key Dependencies

| Layer | Dependency | Why |
|---|---|---|
| API | FastAPI | Async, OpenAPI auto-gen, dependency injection |
| ORM | SQLAlchemy 2.0 | Async support, Mapped/mapped_column style |
| Validation | Pydantic v2 | Schema validation + Field descriptions → API docs |
| Tasks | Celery + Redis | Async parse/index/webhook delivery |
| Search | Elasticsearch 9 | Full-text search over parsed experiment data |
| MCP | FastMCP 3.0 | Agent tool protocol |
| Desktop | Go + fsnotify | Low-overhead file watcher for lab instruments |
| Frontend | React + Vite + Tailwind | SPA with Plotly.js visualizations |

## Data Flow

```
Instrument file
  → Desktop agent (fsnotify) or REST POST /uploads
  → parse_task: detect format → parser → ParsedResult → store PG + S3
  → index_task: index to Elasticsearch
  → webhook_task: fire HMAC-SHA256 webhooks
  → MCP tools / REST API / React frontend
```

## Deployment

- Docker Compose for local dev (`make dev`): PostgreSQL, Redis, Elasticsearch, API server
- Env vars via `LABLINK_*` prefix (see `config.py`)
- Alembic migrations (`make migrate`)
- Tests run without Docker: SQLite + in-memory search + sync tasks (`make test`)
