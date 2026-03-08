# schemas Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `schemas` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Pydantic v2 request/response schemas for the `backend/app` alternative structure. Mirrors `src/lablink/schemas/`.

**Note**: `backend/app/` is an alternative structure. Primary schemas are in `src/lablink/schemas/`.

## Coding Conventions

Follow the same conventions as `src/lablink/schemas/CLAUDE.md`:
- Pydantic v2 `BaseModel` with `ConfigDict(from_attributes=True)` on Response schemas
- `Field(description="...")` on all fields
- Create/Update/Response pattern per domain
- No HTTP concerns in schemas
- `suggestion` field in all error details

## Patterns

Same as `src/lablink/schemas/`. The Envelope[T] pattern and `success_response()`/`error_response()` helpers are the same API.

## Key Dependencies

- `pydantic` v2 — BaseModel, ConfigDict, Field
- `app.schemas.envelope` — Envelope, ErrorDetail, success_response

## Common Gotchas

- This is the `backend/app` version. Primary schemas are in `src/lablink/schemas/`.
- Keep Response schemas in sync with `src/lablink/schemas/` when making API changes.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [src/lablink/schemas/CLAUDE.md](../../../src/lablink/schemas/CLAUDE.md) — primary schemas guide
