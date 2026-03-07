# Design

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Design philosophy, architectural principles, and key patterns used across this codebase.

## Core Philosophy

LabLink is built agent-native from day one. Every feature is designed to be consumable by both humans via UI and AI agents via MCP or REST. Agents are first-class citizens, not an afterthought.

## Architectural Principles

1. **Agent parity** — Every UI action has a corresponding API endpoint. No UI-only features.
2. **Structured outputs** — Every chart/visualization also returns machine-readable JSON.
3. **Composable tools** — API endpoints are atomic primitives (`verb_noun`). Agents compose them.
4. **Errors help agents recover** — Error responses include a `suggestion` field with an actionable fix.
5. **PostgreSQL is source of truth** — ES is eventually consistent. S3 is immutable.
6. **Immutable audit trail** — Append-only with hash chain. Never delete audit events.

## Key Patterns

- **Envelope pattern**: All endpoints return `{ data, meta, errors }` via `Envelope[T]`. See `schemas/envelope.py`.
- **Thin routers / fat services**: Routers validate input and call a service. Zero business logic in routers.
- **BaseParser ABC**: All instrument parsers implement `BaseParser`. Input = bytes + metadata. Output = `ParsedResult`.
- **Task dispatch with sync fallback**: `dispatch_task()` runs inline when `TASK_BACKEND=sync`, uses Celery otherwise.
- **Parser registry**: Auto-detection via `ParserRegistry` + `@register` decorator. No manual wiring.

## What We Avoid

- Business logic in routers — it belongs in services.
- Raw SQL in application code — use SQLAlchemy ORM.
- Deleting audit events — the trail is immutable by design.
- UI-only features — everything must be API-accessible.

## Decision Log

See `decision_history.md` in the repo root for major architectural decisions and their reasoning.
Also see `plans/lablink-product-roadmap.md` for the full 2-year roadmap with design rationale.
