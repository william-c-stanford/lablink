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
- `plans/lablink-product-roadmap.md` — Full 2-year roadmap + MVP spec
- `RESEARCH/` — Market analysis, competitive landscape, agent-native API design, SDL trends

## Documentation Index
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Domain map, package layout, data flow
- [docs/DESIGN.md](./docs/DESIGN.md) — Design philosophy and architectural principles
- [docs/SECURITY.md](./docs/SECURITY.md) — Auth, data protection, threat model
- [docs/FRONTEND.md](./docs/FRONTEND.md) — React/TypeScript/Vite conventions
- [docs/RELIABILITY.md](./docs/RELIABILITY.md) — SLOs, error handling, runbooks
- [docs/QUALITY_SCORE.md](./docs/QUALITY_SCORE.md) — Domain quality grades and gaps
- [docs/PRODUCT_SENSE.md](./docs/PRODUCT_SENSE.md) — Who this is for and why

## Module Guides
| Module | Guide |
|---|---|
| src/lablink/models/ | [models/CLAUDE.md](./src/lablink/models/CLAUDE.md) |
| src/lablink/schemas/ | [schemas/CLAUDE.md](./src/lablink/schemas/CLAUDE.md) |
| src/lablink/routers/ | [routers/CLAUDE.md](./src/lablink/routers/CLAUDE.md) |
| src/lablink/services/ | [services/CLAUDE.md](./src/lablink/services/CLAUDE.md) |
| src/lablink/parsers/ | [parsers/CLAUDE.md](./src/lablink/parsers/CLAUDE.md) |
| src/lablink/tasks/ | [tasks/CLAUDE.md](./src/lablink/tasks/CLAUDE.md) |
| src/lablink/mcp/ | [mcp/CLAUDE.md](./src/lablink/mcp/CLAUDE.md) |

## Gardening
- `/context-gardening:status` — knowledge base health dashboard
- `/context-gardening:tend` — update docs that drifted from code
- `/context-gardening:weed` — find and prune stale docs

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
