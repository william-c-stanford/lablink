# core Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `core` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Core infrastructure for the `backend/app` alternative app structure. Provides database connectivity, password hashing, JWT security, and experiment state machine logic. This is the equivalent of `lablink.database`, `lablink.config`, and parts of `lablink.services` in the primary `src/lablink/` package.

**Note**: `backend/app/` is an alternative structure from the initial Ouroboros scaffold. The primary package is `src/lablink/`. Both coexist and all tests pass with `pythonpath = ["src", "backend"]` in `pyproject.toml`.

## Architecture Within This Module

- `database.py` — SQLAlchemy async engine and session factory
- `hashing.py` — bcrypt password hashing via passlib
- `security.py` — JWT token creation and verification (python-jose)
- `state_machine.py` — Experiment status transition validation

## Coding Conventions

- Follows the same conventions as `src/lablink/` — Pydantic v2, SQLAlchemy 2.0 Mapped style, async-first
- Utility modules (hashing, security) are pure functions with no side effects
- No FastAPI imports in core — this layer is HTTP-agnostic

## Patterns

**Password hashing** (`hashing.py`): `hash_password(plain) → str`, `verify_password(plain, hashed) → bool` via passlib bcrypt.

**JWT** (`security.py`): `create_access_token(data, expires_delta?) → str`, `decode_token(token) → dict`. Uses HS256, configured via environment `SECRET_KEY`.

**State machine** (`state_machine.py`): Validates experiment status transitions. `validate_transition(current, target)` raises `StateTransitionError` if the transition is invalid.

## Key Dependencies

- `sqlalchemy[asyncio]` — async engine
- `passlib[bcrypt]` — password hashing
- `python-jose[cryptography]` — JWT
- `aiosqlite` — dev SQLite driver

## Testing Approach

Unit tests for hashing and security (pure functions). State machine tested via experiment service tests.

## Common Gotchas

- This module is from the `backend/app` scaffold. If you're working on the primary package, look in `src/lablink/` instead.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
