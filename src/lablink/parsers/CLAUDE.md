# parsers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the instrument file parsers layer.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

5 instrument-specific parsers (spectrophotometer, plate reader, HPLC, PCR, balance) plus the `BaseParser` ABC, `ParserRegistry`, `detector`, and `asm_mapper`. Input: raw bytes + file metadata. Output: canonical `ParsedResult` (ASM-compatible). A parser crash must never crash the API — all errors use `ParseError`.

## Coding Conventions

- Every parser subclasses `BaseParser` from `base.py`.
- Parsers must implement: `instrument_types: list[str]`, `can_parse(bytes, filename) -> bool`, `parse(bytes, filename, hint) -> ParsedResult`.
- Raise `ParseError` (not generic exceptions) for any format or content problem.
- Register parsers with `@register` decorator from `registry.py` — no manual wiring needed.
- Treat input bytes as untrusted. Never assume encoding; try UTF-8, fall back to latin-1.

## Patterns Used

- **BaseParser ABC**: `parsers/base.py` — subclass this for every new instrument type.
- **Registry + auto-detect**: `registry.py` exposes `ParserRegistry`. `detector.py` exposes `detect_instrument_type(file_bytes, filename, hint) -> str`. The registry selects the right parser automatically.
- **ASM mapper**: `asm_mapper.py` converts internal `ParsedResult` to Allotropy Schema Model format for interoperability.
- **Fixture-based tests**: Every parser must be tested against real fixture files in `tests/fixtures/`.

## What Belongs Here

- Instrument parser implementations (one file per instrument family).
- `BaseParser` ABC and `ParseError`.
- `ParserRegistry` + `@register` decorator.
- `detect_instrument_type()` — format detection logic.
- `asm_mapper.py` — ASM compatibility layer.

## What Doesn't Belong Here

- File I/O — parsers receive bytes, not file paths.
- Database access — parsers have no DB awareness. Results go to `upload_service` which persists them.
- Business logic — parsers only transform bytes to `ParsedResult`.

## Key Dependencies

- `lablink.schemas.canonical` (`ParsedResult`, `MeasurementValue`, `InstrumentSettings`)
- `csv`, `io` stdlib (CSV parsing)
- No external parser libraries required (allotropy integrated as optional fallback)

## Testing Approach

Each parser must have tests for:
1. Happy path — real fixture file from `tests/fixtures/`
2. Corrupted input — truncated or malformed file → `ParseError` raised (not generic exception)
3. Edge cases — empty file, wrong delimiter, missing columns

Fixture files live in `tests/fixtures/`. Add a new fixture when adding a new parser.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
