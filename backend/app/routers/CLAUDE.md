# routers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `routers` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Thin FastAPI routers for the `backend/app` alternative structure. Mirrors the structure of `src/lablink/routers/`.

**Note**: `backend/app/` is an alternative structure from the initial scaffold. Primary routers are in `src/lablink/routers/`.

## Coding Conventions

Follow the same conventions as `src/lablink/routers/CLAUDE.md`:
- Thin handlers: validate input, call service, return Envelope
- `operation_id` with `verb_noun` snake_case on every route
- `response_model=Envelope[T]`, `response_model_exclude_none=True`
- `success_response()` for all successful responses
- Organization scoping via `get_current_org` dependency

## Patterns

Same as `src/lablink/routers/`. Import from `app.services.*` and `app.schemas.*` instead of `lablink.*`.

## Key Dependencies

- `fastapi` — APIRouter, Depends, Query
- `app.schemas.envelope` — Envelope, success_response
- `app.dependencies` — get_db, get_current_user, get_current_org
- `app.services.*` — service functions

## Common Gotchas

- This is the `backend/app` version. Primary routers are in `src/lablink/routers/`.
- Ensure `operation_id` values are globally unique — they must not duplicate IDs in `src/lablink/routers/` if both are mounted.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [src/lablink/routers/CLAUDE.md](../../../src/lablink/routers/CLAUDE.md) — primary routers guide
