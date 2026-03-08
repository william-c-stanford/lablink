# services Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `services` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Business logic for the `backend/app` alternative structure. Mirrors `src/lablink/services/` — zero HTTP awareness, testable domain logic.

**Note**: `backend/app/` is an alternative structure from the initial Ouroboros scaffold. Primary services are in `src/lablink/services/`. This module contains: `auth.py`, `experiment.py`, `audit.py`, `file_service.py`, `storage.py`.

## Architecture Within This Module

- `auth.py` — User authentication, JWT creation
- `experiment.py` — Experiment CRUD and state machine
- `audit.py` — Audit event recording
- `file_service.py` — File upload orchestration
- `storage.py` — Storage backend abstraction (local/S3)

## Coding Conventions

Follow the same conventions as `src/lablink/services/CLAUDE.md`:
- Zero HTTP awareness: no FastAPI imports
- Raise domain errors, not HTTPException
- `await db.flush()` not `commit()`
- Async throughout
- `suggestion` in all error messages

## Patterns

Same patterns as `src/lablink/services/`. Services take `AsyncSession` (from `app.core.database`), call models, flush on write, return domain objects.

## Key Dependencies

- `app.core.database` — async session
- `app.models.*` — ORM models
- `sqlalchemy` 2.0 — select/execute pattern

## Common Gotchas

- This is the `backend/app` version. For new features, prefer adding to `src/lablink/services/`.
- Never commit inside a service — only flush.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [src/lablink/services/CLAUDE.md](../../../src/lablink/services/CLAUDE.md) — primary services guide
