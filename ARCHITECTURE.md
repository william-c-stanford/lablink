# Architecture — LabLink

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Top-level map of domains and package layering.
> Update this when you add or remove major modules or change how they relate.

## Stack

**Backend**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Celery + Redis / PostgreSQL / Elasticsearch 9 / S3
**Dev mode**: SQLite + aiosqlite, local filesystem storage, in-memory search, sync task fallback (no Docker needed)
**MCP Server**: FastMCP 3.0+ (25 tools across 4 toolsets)
**Frontend**: React + TypeScript + Tailwind + Plotly.js + Vite
**Desktop Agent**: Go 1.22+ (fsnotify + BBolt, file watching for lab instruments)

## Domain Map

| Domain | Path | Responsibility |
|---|---|---|
| API Layer | `src/lablink/routers/` | Thin FastAPI routers — validate, call service, return envelope |
| Business Logic | `src/lablink/services/` | Zero HTTP awareness, testable independently |
| Data Models | `src/lablink/models/` | SQLAlchemy 2.0 ORM (16 models) |
| Request/Response Schemas | `src/lablink/schemas/` | Pydantic v2 schemas, Envelope[T] pattern |
| Instrument Parsers | `src/lablink/parsers/` | BaseParser ABC → 5 instrument parsers |
| Background Tasks | `src/lablink/tasks/` | Celery tasks with sync fallback |
| MCP Server | `src/lablink/mcp/` | 25 FastMCP tools in 4 toolsets |
| Frontend | `frontend/src/` | React SPA with openapi-fetch typed client |
| Desktop Agent | `agent/` | Go file watcher for lab instrument directories |
| Alt Backend | `backend/app/` | Alternative scaffold (from initial build, coexists with src/lablink) |

## Package / Directory Layout

```
lablink/
  src/lablink/            # Primary Python package
    config.py             # pydantic-settings (LABLINK_ prefix env vars)
    database.py           # Async SQLAlchemy engine + session factory
    main.py               # FastAPI app factory
    dependencies.py       # Dependency injection: get_db, get_current_user, get_current_org
    exceptions.py         # LabLinkError hierarchy
    models/               # 16 ORM models (TimestampMixin + SoftDeleteMixin)
    schemas/              # Pydantic v2 schemas + Envelope[T]
    routers/              # 13 thin FastAPI routers
    services/             # 10 service modules (business logic)
    parsers/              # BaseParser ABC + 5 instrument parsers + detector/registry
    tasks/                # Celery tasks (parse, webhook, index) + sync dispatch
    mcp/                  # FastMCP server (25 tools)
  backend/app/            # Alternative structure (coexists, all tests pass)
  frontend/               # React + TypeScript SPA
    src/
      api/                # openapi-fetch typed client + schema.d.ts
      components/         # Feature-based React components
      pages/              # Page-level components (route targets)
      store/              # Zustand stores (auth, ui, filter, events)
  agent/                  # Go desktop agent
    internal/             # File watcher, uploader, heartbeat, queue
  tests/                  # 56 test files, 1,296 tests
  migrations/             # Alembic migrations
  plans/                  # Development plans and roadmap
  RESEARCH/               # Market research, SDL trends, API design docs
```

## Key Dependencies

**Python**: FastAPI, SQLAlchemy 2.0, Pydantic v2, python-jose, passlib, FastMCP, Celery, httpx, allotropy
**JavaScript**: React 18, TypeScript, Tailwind CSS, Zustand, openapi-fetch, Plotly.js, Vite
**Go**: fsnotify, BBolt, standard library
**Infrastructure**: PostgreSQL (prod), SQLite (dev), Elasticsearch 9, Redis (Celery broker), S3 / local filesystem

## Data Flow

```
HTTP/MCP Request
  → Router (validate input, inject deps)
  → Service (business logic, zero HTTP awareness)
  → Model (SQLAlchemy ORM, async session)
  → Database (PostgreSQL/SQLite)
  → Envelope[T] response ({ data, meta, errors })

File Upload Pipeline:
  HTTP POST /uploads → UploadService (hash, dedup, store) → Upload record
  → dispatch_task(parse_upload_file) → ParserService (detect, parse) → ParsedData
  → WebhookService (fire upload.parsed) → IndexTask (Elasticsearch)
```

## Deployment

**Dev**: `uvicorn lablink.main:create_app --factory --reload` (SQLite, no Docker)
**Production**: Docker Compose (PostgreSQL + Redis + Elasticsearch + API + Celery workers)
**Desktop Agent**: Go binary deployed alongside lab instruments, watches directories
