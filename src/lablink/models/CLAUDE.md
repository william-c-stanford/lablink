# models Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `models` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

SQLAlchemy 2.0 ORM models for LabLink. Defines 16 database entities: organization, user, membership, project, instrument, agent, upload, parsed_data, experiment, experiment_upload, campaign, api_token, audit_event, webhook, webhook_delivery, and instrument_data.

This module is the schema of record. Services read from and write to these models. Routers never touch models directly.

## Architecture Within This Module

- `base.py` — Mixins only: `TimestampMixin` (id + timestamps), `SoftDeleteMixin` (deleted_at), `UpdatedAtMixin`. Also re-exports `Base` from `lablink.database` for convenience.
- One file per entity (singular snake_case): `organization.py`, `user.py`, `upload.py`, etc.
- No circular imports — models import from `base.py` and `database.py` only. Cross-model relationships use `relationship()` with string class names where needed.

## Coding Conventions

- **SQLAlchemy 2.0 Mapped style**: Always use `Mapped[type]` + `mapped_column()`. Never use the old Column() style.
- **UUID PKs as String(36)**: UUIDs are stored as `String(36)` for SQLite compatibility. Generated with `default=lambda: str(uuid.uuid4())`.
- **Enum columns**: Use Python `enum.Enum` + `SQLAlchemy Enum(PythonEnum)` for status fields. Define the enum class in the same file as the model.
- **Soft delete via SoftDeleteMixin**: Records are never physically deleted. `deleted_at` is set, `is_deleted` property checks it. Queries must filter `deleted_at.is_(None)` where appropriate.
- **TimestampMixin for standard entities**: Mix `TimestampMixin` into every model that needs `id`, `created_at`, `updated_at`.
- **Table names**: Plural snake_case (`experiments`, `parsed_data`, `audit_events`).

## Patterns

**Mixin composition**:
```python
from lablink.models.base import Base, TimestampMixin, SoftDeleteMixin

class Experiment(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "experiments"
    # Only define columns specific to this model
    intent: Mapped[str] = mapped_column(String(500))
    status: Mapped[ExperimentStatus] = mapped_column(Enum(ExperimentStatus))
```

**Enum definition** (in same file as model):
```python
class UploadStatus(str, enum.Enum):
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    indexed = "indexed"
    parse_failed = "parse_failed"
```

**Foreign keys**: Use `String(36)` for FK columns to match UUID PK type:
```python
organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"))
```

## Key Types and Interfaces

- `TimestampMixin` (`base.py`) — `id: str`, `created_at: datetime`, `updated_at: datetime`
- `SoftDeleteMixin` (`base.py`) — `deleted_at: datetime | None`, `is_deleted: bool` (property)
- `Upload` (`upload.py`) — Central entity for file ingestion; links to org, project, instrument, agent
- `ParsedData` (`parsed_data.py`) — Stores canonical JSON output from parser; linked 1:1 with Upload
- `Experiment` (`experiment.py`) — Tracks experiment lifecycle (PLANNED → RUNNING → COMPLETED/FAILED)
- `AuditEvent` (`audit_event.py`) — Immutable append-only record with SHA-256 hash chain
- `ExperimentUpload` (`experiment_upload.py`) — Association table linking experiments to uploads (M2M)

## What Belongs Here

- SQLAlchemy ORM model class definitions
- Python `enum.Enum` classes for column value types
- `relationship()` declarations
- Table-level indexes and constraints

## What Does Not Belong Here

- Business logic (use `services/`)
- Pydantic schemas (use `schemas/`)
- Database queries or SELECT statements (use `services/`)
- `__init__.py` should only re-export model classes and enum types, not define them

## Key Dependencies

- `sqlalchemy` 2.0+ — Mapped/mapped_column API. Must not fall back to Column() style.
- `lablink.database.Base` — SQLAlchemy DeclarativeBase. Imported via `base.py` re-export.
- No service or router imports. Models are a leaf layer.

## Testing Approach

Model tests are light — the ORM is tested implicitly through service integration tests. If testing a model directly, use the `db` fixture from `tests/conftest.py` which provides an async SQLite session. Verify that mixins auto-populate `id`, `created_at`, `updated_at` on `flush()`.

## Common Gotchas

- **String(36) UUIDs**: Do not use `UUID` column type — it breaks SQLite. Always `String(36)` + `default=lambda: str(uuid.uuid4())`.
- **Soft delete not enforced at DB level**: The `is_deleted` check is application-level. Always add `where(Model.deleted_at.is_(None))` to queries unless you intentionally want deleted records.
- **`Base` is in `database.py`**: Import it via `from lablink.models.base import Base` (the re-export) to avoid circular imports.
- **Enum values must match DB values exactly**: If you rename an enum value, write a migration to update existing rows.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
