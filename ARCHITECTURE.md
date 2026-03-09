# Architecture — LabLink

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-09 -->

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
| Data Models | `src/lablink/models/` | SQLAlchemy 2.0 ORM (17 models) |
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
  tests/                  # 56 test files, 1,423 unit tests + 29 E2E tests
    e2e/                  # Playwright E2E suite (run via `make e2e`, separate from unit tests)
  migrations/             # Alembic migrations
  infra/                  # Terraform modules (ECS, RDS, Redis, ES, S3, VPC)
  plans/                  # Forwarding stubs → docs/execution-plans/ and docs/product-specs/
  RESEARCH/               # Market research, SDL trends, API design docs
  llms.txt                # Progressive disclosure: quick API overview for agents
  llms-full.txt           # Progressive disclosure: full tool reference for agents
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
**CI/CD**: GitHub Actions — lint + type-check + unit tests on every PR; E2E tests on main push or `run-e2e` label; deploy pipeline triggers on merge to main
**Production**: Docker (multi-stage `Dockerfile` for API, `Dockerfile.worker` for Celery); provisioned via Terraform (`infra/`) on AWS ECS + RDS + ElastiCache + OpenSearch + S3
**Desktop Agent**: Go binary deployed alongside lab instruments, watches directories
