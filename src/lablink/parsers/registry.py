"""Parser registry: maps instrument_type to parser class with auto-detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lablink.parsers.base import BaseParser


class ParserRegistry:
    """Registry of available instrument parsers."""

    _parsers: dict[str, type[BaseParser]] = {}

    @classmethod
    def register(cls, parser_class: type[BaseParser]) -> type[BaseParser]:
        """Register a parser class by its instrument_type."""
        cls._parsers[parser_class.instrument_type] = parser_class
        return parser_class

    @classmethod
    def get(cls, instrument_type: str) -> type[BaseParser] | None:
        """Get a parser class by instrument_type."""
        return cls._parsers.get(instrument_type)

    @classmethod
    def all(cls) -> dict[str, type[BaseParser]]:
        """Return all registered parsers."""
        return dict(cls._parsers)

    @classmethod
    def detect(cls, file_bytes: bytes, filename: str | None = None) -> type[BaseParser] | None:
        """Auto-detect the best parser for a file based on confidence scores."""
        best_score = 0.0
        best_parser = None
        for parser_class in cls._parsers.values():
            parser = parser_class()
            score = parser.detect(file_bytes, filename)
            if score > best_score:
                best_score = score
                best_parser = parser_class
        return best_parser if best_score > 0.0 else None
