# parsers Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `parsers` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Instrument file parsers for LabLink. Takes raw file bytes from lab instruments and produces canonical `ParsedResult` objects. Supports: spectrophotometer (NanoDrop/Cary), plate reader (SoftMax Pro/Gen5), HPLC (Agilent/Shimadzu), PCR (Bio-Rad CFX/QuantStudio), and balance (Mettler Toledo/Sartorius).

The registry auto-detects the best parser for any given file. The canonical output schema is ASM-compatible (`ParsedResult` from `schemas/canonical.py`).

## Architecture Within This Module

- `base.py` — `BaseParser` ABC and `ParseError` exception
- `registry.py` — `ParserRegistry` with `@register` decorator + `get_best_parser()`
- `detector.py` — `detect_instrument_type(file_bytes, filename, hint)` for confidence-scored detection
- `asm_mapper.py` — Allotropy ASM mapper for graceful fallback to the allotropy library
- Five instrument parsers: `spectrophotometer.py`, `plate_reader.py`, `hplc.py`, `pcr.py`, `balance.py`

## Coding Conventions

- **Inherit `BaseParser`**: Every parser must subclass `BaseParser` and implement `parse()`.
- **Class-level attributes required**: `name: ClassVar[str]`, `version: ClassVar[str]`, `instrument_type: ClassVar[str]`, `supported_extensions: ClassVar[list[str]]`
- **Raise `ParseError`, never crash**: Malformed inputs must raise `ParseError(message, parser_name, suggestion)`. Never let unhandled exceptions propagate.
- **`detect()` returns 0.0-1.0**: The default checks file extension (returns 0.5 on match). Override for header-based detection to return higher confidence.
- **Register via decorator**: Use `@registry.register` after defining the class.
- **Suggestion field always set**: `ParseError.suggestion` defaults to "Check file format. Use list_parsers to see supported formats." — override if you can be more specific.

## Patterns

**Implementing a new parser**:
```python
from lablink.parsers.base import BaseParser, ParseError
from lablink.parsers.registry import registry
from lablink.schemas.canonical import ParsedResult

class MyInstrumentParser(BaseParser):
    name: ClassVar[str] = "my_instrument"
    version: ClassVar[str] = "1.0"
    instrument_type: ClassVar[str] = "my_instrument"
    supported_extensions: ClassVar[list[str]] = [".csv", ".txt"]

    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        try:
            # parse logic here
            ...
        except Exception as exc:
            raise ParseError(
                f"Cannot parse MyInstrument file: {exc}",
                parser_name=self.name,
                suggestion="Ensure file is exported in default CSV format from MyInstrument software.",
            ) from exc

registry.register(MyInstrumentParser)
```

**Confidence-based detection** (override `detect()`):
```python
def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
    # Return 0.9 if you see a distinctive header
    header = file_bytes[:200].decode("utf-8", errors="replace")
    if "NanoDrop" in header:
        return 0.9
    return super().detect(file_bytes, filename)  # falls back to extension check
```

## Key Types and Interfaces

- `BaseParser` (`base.py:36`) — ABC. Implement `parse(bytes, dict|None) → ParsedResult` and optionally `detect(bytes, str|None) → float`
- `ParseError` (`base.py:15`) — Structured error with `parser_name`, `message`, `suggestion`
- `ParsedResult` (`schemas/canonical.py`) — Canonical output: `measurements`, `instrument_type`, `parser_name`, `sample_count`, `settings`
- `ParserRegistry` (`registry.py`) — Holds all registered parsers; `get_best_parser(bytes, filename)` returns highest-confidence parser

## What Belongs Here

- `BaseParser` subclasses for specific instrument types
- Instrument-specific CSV/TSV parsing logic
- `detect()` overrides for header-based instrument identification
- The registry, detector, and ASM mapper utilities

## What Does Not Belong Here

- Database access (parsers are pure functions: bytes → ParsedResult)
- HTTP handling or FastAPI concerns
- File I/O (parsers receive bytes, not file paths)
- Pydantic schema definitions (those are in `schemas/canonical.py`)

## Key Dependencies

- `lablink.schemas.canonical.ParsedResult` — output type for all parsers
- `allotropy` — optional fallback library (imported gracefully in `asm_mapper.py`)
- Standard library only: `csv`, `io`, `re` — no heavy parsing dependencies

## Testing Approach

Each parser must have tests using real fixture files from `tests/fixtures/`. Required test cases per parser:
1. **Happy path**: Parse a real fixture file, assert measurement count, instrument type, sample names
2. **Corrupted input**: Pass garbage bytes, assert `ParseError` is raised (not crash)
3. **Edge case**: Empty file, missing headers, wrong delimiter, etc.

Fixture files are in `tests/fixtures/` — 24 real instrument data files (CSV/TSV). Add new fixtures when adding new parsers.

## Common Gotchas

- **allotropy is optional**: `asm_mapper.py` imports allotropy inside a try/except. Don't assume it's available at parse time.
- **Don't catch `ParseError`**: In the parser's own `parse()`, let `ParseError` propagate. Only catch `Exception` to re-raise as `ParseError`.
- **Encoding**: Instrument CSVs often use Windows-1252 or Latin-1 encoding. Use `errors="replace"` or try multiple encodings before failing.
- **BOM stripping**: Some instruments write UTF-8 BOM. Strip with `file_bytes.lstrip(b'\xef\xbb\xbf')`.
- **Registry is module-level**: Parsers are registered at import time. Ensure the parser file is imported (the `__init__.py` should import all parsers to trigger registration).

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../../docs/DESIGN.md)
