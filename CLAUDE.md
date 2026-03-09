# LabLink Development Conventions

## Stack
- Backend: Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Celery + Redis / PostgreSQL / Elasticsearch / S3
- Frontend: React + TypeScript + Tailwind + Plotly.js + Vite (planned)
- Desktop Agent: Go 1.22+ (fsnotify + BBolt) (planned)
- MCP Server: FastMCP 3.0+
- Dev mode: SQLite + aiosqlite, local filesystem storage, in-memory search, sync tasks

## Architecture Principles
1. **Agent parity**: Every UI action has a corresponding API endpoint. No UI-only features.
2. **Structured outputs**: Every chart/visualization also returns machine-readable JSON.
3. **Composable tools**: API endpoints are atomic primitives (verb_noun). Agents compose them.
4. **Response envelope**: All endpoints return { data, meta, errors } via Envelope[T].
5. **Errors help agents recover**: Error responses include `suggestion` field with actionable fix.
6. **PostgreSQL is source of truth**: ES is eventually consistent. S3 is immutable.
7. **Immutable audit trail**: Append-only with hash chain. Never delete audit events.

## Project Structure
```
src/lablink/
  config.py              # Settings via pydantic-settings (env vars, LABLINK_ prefix)
  database.py            # Async SQLAlchemy engine, session factory, Base
  main.py                # FastAPI app factory, CORS, exception handlers, router registration
  dependencies.py        # get_db, get_current_user, get_current_org, require_role
  exceptions.py          # LabLinkError hierarchy (NotFound, Validation, StateTransition, etc.)
  schemas/               # Pydantic v2 request/response schemas
    envelope.py          # Envelope[T], ErrorDetail, success_response(), error_response()
    canonical.py         # ParsedResult, MeasurementValue, InstrumentSettings (ASM-compatible)
    auth.py, organizations.py, projects.py, instruments.py, agents.py,
    uploads.py, experiments.py, campaigns.py, webhooks.py, audit.py
  models/                # SQLAlchemy 2.0 ORM models (Mapped/mapped_column, String(36) UUID PKs)
    base.py              # TimestampMixin, UpdatedAtMixin, SoftDeleteMixin
    16 model files       # organization, user, membership, project, instrument, agent,
                         # upload, parsed_data, experiment, experiment_upload, campaign,
                         # api_token, audit_event, webhook, webhook_delivery
  routers/               # Thin FastAPI routers (validate -> call service -> return envelope)
    13 router files      # auth, organizations, projects, instruments, agents, uploads,
                         # data, experiments, campaigns, webhooks, audit, admin
  services/              # Business logic (zero HTTP awareness, testable independently)
    10 service files     # auth, organization, upload, parser, search, experiment,
                         # campaign, webhook, audit, export
  parsers/               # Instrument file parsers (BaseParser ABC)
    base.py              # BaseParser ABC, ParseError
    registry.py          # ParserRegistry with @register decorator and auto-detect
    detector.py          # detect_instrument_type(file_bytes, filename, hint)
    spectrophotometer.py # NanoDrop/Cary UV-Vis CSV
    plate_reader.py      # SoftMax Pro/Gen5 template-based CSV (96/384-well)
    hplc.py              # Agilent ChemStation/Shimadzu LabSolutions CSV
    pcr.py               # Bio-Rad CFX/Thermo QuantStudio CSV (Ct values)
    balance.py           # Mettler Toledo/Sartorius CSV
  tasks/                 # Celery tasks with sync fallback
    dispatch.py          # dispatch_task() - inline when TASK_BACKEND="sync"
    celery_app.py        # Celery config with parsing/webhooks/indexing queues
    parse_task.py        # Parse upload file, store result, fire webhook, queue index
    webhook_task.py      # Deliver webhook with HMAC-SHA256, retry with backoff
    index_task.py        # Index parsed data to search service
  mcp/                   # FastMCP server (25 tools, 4 toolsets + 2 discovery)
    server.py            # Standalone: python -m lablink.mcp.server
backend/                 # Alternative app structure (from initial scaffold)
tests/                   # pytest with asyncio_mode=auto
  fixtures/              # 24 realistic instrument data files (CSV/TSV)
migrations/              # Alembic migrations
```

## Code Organization
- **Routers are thin**: validate input, call service, return envelope. No business logic.
- **Services contain business logic**: zero HTTP awareness, testable independently.
- **Parsers follow BaseParser ABC**: input (bytes + metadata), output ParsedResult.
- **Models use SQLAlchemy 2.0**: Mapped/mapped_column style, String(36) UUID PKs for SQLite compat.
- **Schemas use Pydantic v2**: Field descriptions (become API docs + MCP tool descriptions), ConfigDict(from_attributes=True) on response models.

## Naming Conventions
- API operation_ids: verb_noun snake_case (`list_experiments`, `create_upload`)
- Database tables: plural snake_case (`experiments`, `parsed_data`)
- Python files: singular snake_case (`experiment.py`, `upload_service.py`)
- Pydantic schemas: PascalCase (`ExperimentCreate`, `UploadResponse`)
- MCP tools: verb_noun snake_case (`search_catalog`, `get_instrument_data`)

## Envelope Pattern
Every endpoint returns:
```python
{
  "data": T | null,           # The response payload
  "meta": {
    "request_id": "uuid",
    "timestamp": "iso8601",
    "pagination": { "total_count", "page", "page_size", "has_more" } | null
  },
  "errors": [{
    "code": "MACHINE_READABLE",
    "message": "Human readable",
    "field": "optional_field",
    "suggestion": "Agent-actionable recovery hint",
    "retry": false,
    "retry_after": null
  }]
}
```

## MCP Server (25 tools)
- **Discovery**: list_toolsets, get_toolset
- **Explorer (8)**: list_experiments, get_experiment, get_instrument_data, search_catalog, list_instruments, list_uploads, get_chart_data, create_export
- **Planner (7)**: create_experiment, update_experiment, record_outcome, link_upload_to_experiment, create_campaign, get_campaign_progress, list_campaigns
- **Ingestor (4)**: create_upload, list_parsers, get_upload, reparse_upload
- **Admin (4)**: get_usage_stats, list_agents, create_webhook, list_audit_events

## Testing
- pytest with asyncio_mode="auto"
- Use httpx.AsyncClient with ASGITransport for API tests
- Override dependencies via app.dependency_overrides
- Parser tests use real fixture files in tests/fixtures/
- Every parser must have tests for: happy path, corrupted input, edge cases
- Tests work without Docker (SQLite + mocks)

## Running
- `make dev` — Start Docker services + API server
- `make test` — Run test suite (1,296 tests, no Docker needed)
- `make lint` — Ruff + mypy
- `make migrate` — Run Alembic migrations
- `make format` — Auto-format with ruff

## Key References
- `docs/product-specs/lablink-product-roadmap.md` — Full 2-year roadmap + MVP spec
- `RESEARCH/` — Market analysis, competitive landscape, agent-native API design, SDL trends

## Module Guides

Each source module has a `CLAUDE.md` with local coding conventions (lazy-loaded by Claude Code).

| Module | Guide |
|---|---|
| src/lablink/models/ | [models/CLAUDE.md](./src/lablink/models/CLAUDE.md) |
| src/lablink/parsers/ | [parsers/CLAUDE.md](./src/lablink/parsers/CLAUDE.md) |
| src/lablink/routers/ | [routers/CLAUDE.md](./src/lablink/routers/CLAUDE.md) |
| src/lablink/schemas/ | [schemas/CLAUDE.md](./src/lablink/schemas/CLAUDE.md) |
| src/lablink/services/ | [services/CLAUDE.md](./src/lablink/services/CLAUDE.md) |
| src/lablink/tasks/ | [tasks/CLAUDE.md](./src/lablink/tasks/CLAUDE.md) |
| frontend/src/api/ | [api/CLAUDE.md](./frontend/src/api/CLAUDE.md) |
| frontend/src/components/ | [components/CLAUDE.md](./frontend/src/components/CLAUDE.md) |
| frontend/src/pages/ | [pages/CLAUDE.md](./frontend/src/pages/CLAUDE.md) |
| frontend/src/store/ | [store/CLAUDE.md](./frontend/src/store/CLAUDE.md) |

## Documentation

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Stack, domain map, data flow, deployment |
| [docs/DESIGN.md](./docs/DESIGN.md) | Design philosophy, principles, patterns |
| [docs/SECURITY.md](./docs/SECURITY.md) | Auth patterns, threat model |
| [docs/FRONTEND.md](./docs/FRONTEND.md) | Frontend conventions and component patterns |
| [docs/RELIABILITY.md](./docs/RELIABILITY.md) | SLOs, error handling, runbooks |
| [docs/QUALITY_SCORE.md](./docs/QUALITY_SCORE.md) | Domain quality grades and gaps |
| [docs/PRODUCT_SENSE.md](./docs/PRODUCT_SENSE.md) | Product principles and target users |
| [docs/PLANS.md](./docs/PLANS.md) | Plans catalogue |
| [docs/gardening-log.md](./docs/gardening-log.md) | Context-gardening run history |
| [docs/generated/db-schema.md](./docs/generated/db-schema.md) | Auto-generated database schema reference (17 tables) |

<!-- ooo:START -->
<!-- ooo:VERSION:0.14.0 -->
## Ouroboros Commands

| Command | Loads |
|---------|-------|
| `ooo interview` | `ouroboros:socratic-interviewer` |
| `ooo seed` | `ouroboros:seed-architect` |
| `ooo run` | MCP required |
| `ooo evaluate` | `ouroboros:evaluator` |
| `ooo unstuck` | `ouroboros:{persona}` |
| `ooo status` | MCP: `session_status` |
| `ooo setup` | — |
| `ooo help` | — |
<!-- ooo:END -->
