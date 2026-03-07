# models Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the SQLAlchemy ORM models layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

16 SQLAlchemy 2.0 ORM models covering the full LabLink domain: organizations, users, memberships, projects, instruments, agents, uploads, parsed data, experiments, campaigns, API tokens, audit events, and webhooks. All models are registered with `Base.metadata` via `models/__init__.py`.

## Coding Conventions

- Use SQLAlchemy 2.0 `Mapped[T]` / `mapped_column()` style — not the legacy `Column()` API.
- Primary keys are `String(36)` UUIDs for SQLite/PostgreSQL compatibility.
- All models include `TimestampMixin` (`created_at`, `updated_at`) from `base.py`.
- Soft-delete models use `SoftDeleteMixin` — never hard-delete rows with soft delete.
- Table names are plural snake_case (e.g., `organizations`, `parsed_data`, `audit_events`).

## Patterns Used

- **Mixins**: `TimestampMixin`, `UpdatedAtMixin`, `SoftDeleteMixin` in `base.py` — compose these, don't repeat the columns.
- **UUID PKs as String(36)**: `id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))`.
- **Relationships**: Declare with `relationship()` and `back_populates` for bidirectional links.
- **Enums**: Database enums use Python `enum.Enum`. Import from the model file where they're defined.

## What Belongs Here

- SQLAlchemy ORM model classes and their column/relationship definitions.
- Model-level enums and constants (e.g., `UploadStatus`, `ExperimentState`).
- The `base.py` mixins: `TimestampMixin`, `SoftDeleteMixin`, etc.
- The `__init__.py` re-export so consumers can do `from lablink.models import Upload, AuditEvent`.

## What Doesn't Belong Here

- Business logic — that lives in `services/`.
- Query logic beyond simple relationships — complex queries belong in services.
- Pydantic schemas — those live in `schemas/`.

## Key Dependencies

- `sqlalchemy` 2.0 (ORM + async engine via `database.py`)
- `uuid` stdlib (primary key generation)
- `lablink.database` (`Base`)

## Testing Approach

Models are tested indirectly via service and router tests using an in-memory SQLite database. Direct model tests (if needed) should use `pytest-asyncio` with the test session factory from `tests/conftest.py`.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
