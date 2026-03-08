# parsers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `parsers` module (backend/app alternative structure).
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Instrument file parsers for the `backend/app` alternative structure. Mirrors `src/lablink/parsers/` — takes raw file bytes and produces canonical parsed results.

**Note**: `backend/app/` is an alternative structure. The primary parsers are in `src/lablink/parsers/`. Both coexist.

## Coding Conventions

Follow the same conventions as `src/lablink/parsers/CLAUDE.md`:
- Inherit `BaseParser` ABC
- Implement `parse(bytes, metadata?) → ParsedResult`
- Raise `ParseError` on malformed input, never raw exceptions
- `detect() → float` for confidence-scored auto-detection
- Register via `@registry.register`

## Patterns

Same as `src/lablink/parsers/`. Import from `app.parsers.base` instead of `lablink.parsers.base`.

## Key Dependencies

- `app.parsers.base.BaseParser`, `ParseError` — from this package
- `allotropy` — optional fallback (imported gracefully)
- Standard library CSV/IO utilities

## Testing Approach

Use real fixture files from `tests/fixtures/`. Test happy path, corrupted input, and edge cases for each parser.

## Common Gotchas

- This is the `backend/app` version. The primary parsers are in `src/lablink/parsers/`.
- Parser registration is shared across import-time. Don't double-register parsers by importing both `lablink.parsers` and `app.parsers` in the same process.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [src/lablink/parsers/CLAUDE.md](../../../src/lablink/parsers/CLAUDE.md) — primary parsers guide
