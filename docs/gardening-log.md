# Documentation Gardening Log

## 2026-03-09 — Garden Run

- **Updated:** `src/lablink/models/CLAUDE.md` — entity count 16→17; added ExperimentPredecessor to purpose list and Key Types section
- **Updated:** `ARCHITECTURE.md` — model count 16→17 in domain map; added infra/, llms.txt/llms-full.txt to directory layout; expanded Deployment section with CI/CD and Terraform details
- **Updated:** `docs/RELIABILITY.md` — deploy runbook updated to reflect GitHub Actions CI/CD pipeline and Terraform prod path
- **Skipped:** `src/lablink/parsers/CLAUDE.md` — parser changes were import-only cleanups, no behavioral changes
- **Skipped:** `src/lablink/routers/CLAUDE.md` — router changes were import-only cleanups
- **Skipped:** `src/lablink/schemas/CLAUDE.md` — schema changes were import-only cleanups
- **Skipped:** `src/lablink/services/CLAUDE.md` — service changes were import-only cleanups
- **Skipped:** `src/lablink/tasks/CLAUDE.md` — task changes were import-only cleanups
- **Skipped:** `docs/DESIGN.md` — no API surface or pattern changes
- **Skipped:** `plans/*.md` — already forwarding stubs, no migration needed
- **Generated:** `docs/gardening-log.md` — created this log

## 2026-03-09 — Garden Run (2)

- **Skipped:** `src/lablink/mcp/server.py` — removed `from __future__ import annotations`; implementation-only fix, no API/convention change
- **Generated:** `docs/generated/db-schema.md` — first generation from SQLAlchemy models (17 tables)

## 2026-03-09 — Garden Run (3)

- **Skipped:** all src/ and tests/ files — `1becf3d reformatted tests` was purely formatting (line-wrapping); no API, model, or pattern changes

## 2026-03-09 — Garden Run (4)

- **Updated:** `src/lablink/models/CLAUDE.md` — added TYPE_CHECKING cross-model import pattern (established across all 13 model files in the mypy fix commit)
- **Updated:** `backend/app/mcp_server/CLAUDE.md` — added gotcha: do not use `from __future__ import annotations` in FastMCP tool files (causes NameError at decoration time when pydantic evaluates lazy annotation strings)
- **Skipped:** `src/lablink/services/CLAUDE.md` — `WebhookService.list` rename is implementation-only; CLAUDE.md doesn't enumerate method names
- **Skipped:** `src/lablink/routers/CLAUDE.md`, `src/lablink/schemas/CLAUDE.md` — type annotation fixes only
- **Skipped:** `ARCHITECTURE.md` — mypy added to dev deps but ARCHITECTURE.md covers prod stack, not toolchain versions
- **Skipped:** `docs/generated/db-schema.md` — model changes were import-only (TYPE_CHECKING); no schema columns/tables changed
