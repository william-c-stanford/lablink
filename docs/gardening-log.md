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
