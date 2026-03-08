# Design

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Design philosophy, architectural principles, and key patterns used across this codebase.

## Core Philosophy

LabLink is built agent-native from day one. Every feature must be accessible to both humans (via UI) and agents (via API/MCP), with the same capability surface. Agents are first-class consumers, not an afterthought.

The platform is the data backbone for research labs evolving into self-driving labs (SDLs). This shapes every decision: structured outputs alongside visualizations, composable atomic tools, and errors that help agents self-correct.

## Architectural Principles

1. **Agent parity**: Every UI action has a corresponding API endpoint. No UI-only features.
2. **Envelope[T] everywhere**: All responses return `{ data, meta, errors }` with `suggestion` fields in errors for agent-actionable recovery.
3. **Thin routers, fat services**: Routers validate and delegate. All business logic lives in services with zero HTTP awareness.
4. **Composable atomic tools**: API endpoints are verb_noun primitives. Agents compose them. No god-endpoints.
5. **Immutable audit trail**: Append-only with SHA-256 hash chain. Never delete audit events.
6. **Progressive disclosure**: `llms.txt` → `llms-full.txt` → OpenAPI → MCP server. Agents pick their depth.

## Key Patterns

**Envelope Pattern**: Every endpoint returns `Envelope[T]` via `success_response()` or `error_response()`. The `errors[].suggestion` field is always populated with agent-actionable recovery hints. See `src/lablink/schemas/envelope.py`.

**BaseParser ABC**: All instrument parsers inherit `BaseParser`, implement `parse(bytes, metadata) → ParsedResult` and `detect(bytes, filename) → float`. Registry auto-detects the best parser. See `src/lablink/parsers/base.py`.

**Storage Abstraction**: `StorageBackend` ABC with `LocalStorageBackend` (dev) and `S3StorageBackend` (prod). Swapped by config, transparent to services. See `src/lablink/services/upload_service.py`.

**Dispatch Fallback**: `dispatch_task()` runs inline when `TASK_BACKEND=sync` (dev) or routes to Celery (prod). Zero infrastructure needed for development. See `src/lablink/tasks/dispatch.py`.

**SQLAlchemy 2.0 Mapped Style**: All models use `Mapped[type]` + `mapped_column()` syntax. UUID PKs stored as `String(36)` for SQLite compatibility. Mixins in `base.py` for common columns.

## What We Avoid

- **HTTP awareness in services**: Services never import FastAPI types or access request objects.
- **Mocking the database in tests**: API tests use `httpx.AsyncClient` with `ASGITransport` against a real (SQLite) DB.
- **UI-only actions**: If an action exists in the UI, it must exist as an API endpoint too.
- **Deleting audit records**: The audit trail is append-only and hash-chained. Never soft-delete it.
- **God endpoints**: Large monolithic endpoints that do too much. Prefer composable atomic primitives.

## Decision Log

- **SQLite for dev**: Enables zero-Docker development. All 1,296 tests pass without Docker. `String(36)` PKs ensure SQLite compat.
- **Own parsers over allotropy-only**: Custom `BaseParser` ABC with graceful allotropy fallback gives control over parsing logic and canonical schema.
- **Per-lab pricing**: Not per-seat, which mirrors how labs actually think about budgets.
- **File watching as primary ingestion**: 70-80% of lab instruments write CSV files. File watching covers the majority without requiring real-time instrument APIs.

## Design Docs

See [docs/design-docs/index.md](./design-docs/index.md) for the full catalogue of design documents.

Core beliefs: [docs/design-docs/core-beliefs.md](./design-docs/core-beliefs.md)
