# Documentation Gardening Log

## 2026-03-09 — Garden Run (8)

- **Skipped:** all candidates — only formatting/style reformats since run 7; no behavioral changes

## 2026-03-09 — Garden Run (7)

- **Updated:** `ARCHITECTURE.md` — test count 1,296→1,423 unit + 29 E2E; added `tests/e2e/` to directory layout; updated CI/CD line to note E2E job on main/`run-e2e` label
- **Updated:** `docs/RELIABILITY.md` — added Testing section: `make test` vs `make e2e`, 1,423 unit + 29 E2E tests, CI E2E trigger conditions
- **Updated:** `docs/FRONTEND.md` — added E2E testing note; added Dev Server Configuration section documenting `VITE_API_BASE_URL` proxy override; updated last-reviewed date
- **Updated:** `src/lablink/services/CLAUDE.md` — fixed state machine example to use lowercase enum members (`ExperimentStatus.planned`) matching the fixed `experiment_service.py`; updated last-reviewed date
- **Skipped:** `frontend/src/pages/CLAUDE.md` — page list already current; no structural changes
- **Skipped:** `docs/generated/db-schema.md` — no model/migration changes since last run

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

## 2026-03-09 — Garden Run (5)

- **Updated:** `CLAUDE.md` — added `docs/gardening-log.md` and `docs/generated/db-schema.md` to Documentation table (both existed but were unreachable from CLAUDE.md)

## 2026-03-09 — Garden Run (6)

- **Skipped:** `src/lablink/CLAUDE.md` — file does not exist; lint heuristic false positive (model docs live in `src/lablink/models/CLAUDE.md`, already updated in run 4)
- **Skipped:** `docs/generated/db-schema.md` — commit `68fa954` added only blank lines and `if TYPE_CHECKING:` import blocks to model files; no schema columns or tables changed
- **Skipped:** `docs/DESIGN.md` — no API surface or design pattern changes in reformatting commit

## 2026-03-09 — Garden Run (4)

- **Updated:** `src/lablink/models/CLAUDE.md` — added TYPE_CHECKING cross-model import pattern (established across all 13 model files in the mypy fix commit)
- **Updated:** `backend/app/mcp_server/CLAUDE.md` — added gotcha: do not use `from __future__ import annotations` in FastMCP tool files (causes NameError at decoration time when pydantic evaluates lazy annotation strings)
- **Skipped:** `src/lablink/services/CLAUDE.md` — `WebhookService.list` rename is implementation-only; CLAUDE.md doesn't enumerate method names
- **Skipped:** `src/lablink/routers/CLAUDE.md`, `src/lablink/schemas/CLAUDE.md` — type annotation fixes only
- **Skipped:** `ARCHITECTURE.md` — mypy added to dev deps but ARCHITECTURE.md covers prod stack, not toolchain versions
- **Skipped:** `docs/generated/db-schema.md` — model changes were import-only (TYPE_CHECKING); no schema columns/tables changed
