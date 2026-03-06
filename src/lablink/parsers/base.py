"""Base parser ABC for all instrument parsers.

Every parser must inherit from BaseParser and implement the `parse` method.
Input: raw file bytes + metadata dict. Output: ParsedResult.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from lablink.schemas.canonical import ParsedResult


class ParseError(Exception):
    """Raised when a parser cannot process the input file.

    Attributes:
        parser_name: Name of the parser that failed.
        message: Human-readable error description.
        suggestion: Agent-oriented suggestion for recovery.
    """

    def __init__(
        self,
        message: str,
        parser_name: str = "unknown",
        suggestion: str | None = None,
    ) -> None:
        self.parser_name = parser_name
        self.message = message
        self.suggestion = suggestion or "Check file format. Use list_parsers to see supported formats."
        super().__init__(message)


class BaseParser(ABC):
    """Abstract base class for instrument file parsers.

    Subclasses must define class-level attributes and implement `parse()`.
    """

    # Subclasses must override these
    name: ClassVar[str]
    version: ClassVar[str]
    instrument_type: ClassVar[str]
    supported_extensions: ClassVar[list[str]]

    @abstractmethod
    def parse(self, file_bytes: bytes, metadata: dict | None = None) -> ParsedResult:
        """Parse raw instrument file bytes into canonical ParsedResult.

        Args:
            file_bytes: Raw file content.
            metadata: Optional metadata dict (instrument_type hint, filename, etc.).

        Returns:
            ParsedResult with measurements, settings, and metadata.

        Raises:
            ParseError: If the file cannot be parsed (not a crash, a structured error).
        """
        ...

    def detect(self, file_bytes: bytes, filename: str | None = None) -> float:
        """Return a confidence score (0.0-1.0) that this parser can handle the file.

        Default implementation checks file extension. Subclasses can override
        for header-based detection.

        Args:
            file_bytes: Raw file content.
            filename: Original filename (optional).

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        if filename:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if f".{ext}" in self.supported_extensions:
                return 0.5
        return 0.0
