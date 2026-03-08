# models Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `models` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

SQLAlchemy 2.0 ORM models for the `backend/app` alternative structure. Mirrors the structure of `src/lablink/models/` but may have slight differences from the Ouroboros initial scaffold.

**Note**: `backend/app/` is an alternative structure. The primary models are in `src/lablink/models/`. Both coexist via `pythonpath = ["src", "backend"]`.

## Coding Conventions

Same as `src/lablink/models/`:
- SQLAlchemy 2.0 `Mapped[type]` + `mapped_column()` style
- `String(36)` UUID PKs for SQLite compatibility
- `TimestampMixin`, `SoftDeleteMixin` for common columns
- Plural snake_case table names
- Enum classes defined alongside the model that uses them

## Patterns

Follow the same patterns as `src/lablink/models/CLAUDE.md`. The key difference is the import path: `from app.core.database import Base` instead of `from lablink.database import Base`.

## Key Dependencies

- `app.core.database.Base` — DeclarativeBase from the app/core package
- `sqlalchemy` 2.0 — `Mapped`, `mapped_column`

## Common Gotchas

- This is the `backend/app` version. If you're in the primary package, use `src/lablink/models/` instead.
- Import `Base` from `app.core.database`, not from `app.models.base` or anywhere else.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [src/lablink/models/CLAUDE.md](../../../src/lablink/models/CLAUDE.md) — primary models guide
