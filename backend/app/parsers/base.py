"""Base parser abstract class and error types.

All 5 instrument parsers inherit from BaseParser and implement
the parse() method to produce a canonical ParsedResult.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.schemas.parsed_result import InstrumentSettings, ParsedResult


@dataclass
class FileContext:
    """Metadata about the file being parsed, provided by the upload pipeline."""

    file_name: str
    file_bytes: bytes
    instrument_type_hint: str | None = None
    org_id: str | None = None
    upload_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def file_hash(self) -> str:
        """SHA-256 hex digest of file contents."""
        return hashlib.sha256(self.file_bytes).hexdigest()

    @property
    def text(self) -> str:
        """Decode file bytes as UTF-8 (with fallback to latin-1)."""
        try:
            return self.file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return self.file_bytes.decode("latin-1")

    @property
    def extension(self) -> str:
        """Lowercase file extension with dot, e.g. '.csv'."""
        if "." in self.file_name:
            return "." + self.file_name.rsplit(".", 1)[-1].lower()
        return ""


class ParseError(Exception):
    """Raised when a parser cannot extract valid data from an instrument file.

    Includes a suggestion field for agent-native error recovery.
    """

    def __init__(
        self,
        message: str,
        *,
        parser_name: str = "",
        file_name: str = "",
        suggestion: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.parser_name = parser_name
        self.file_name = file_name
        self.suggestion = suggestion or "Check that the file format matches the selected instrument type."
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API error responses."""
        return {
            "error": str(self),
            "parser_name": self.parser_name,
            "file_name": self.file_name,
            "suggestion": self.suggestion,
            "details": self.details,
        }


class BaseParser(ABC):
    """Abstract base class for all instrument file parsers.

    Subclasses must implement:
        - parse(ctx: FileContext) -> ParsedResult
        - can_handle(ctx: FileContext) -> bool

    Class attributes:
        - name: human-readable parser name
        - version: semver string
        - instrument_type: one of spectrophotometer, plate_reader, hplc, pcr, balance
        - supported_extensions: tuple of file extensions (e.g. (".csv", ".txt"))
    """

    name: ClassVar[str]
    version: ClassVar[str]
    instrument_type: ClassVar[str]
    supported_extensions: ClassVar[tuple[str, ...]]

    def safe_parse(self, ctx: FileContext) -> ParsedResult:
        """Parse with a safety net that converts unexpected exceptions to ParseError.

        This wraps parse() to ensure that corrupted or unexpected input
        never causes an unhandled exception — only ParseError is raised.
        """
        if not ctx.file_bytes:
            raise ParseError(
                f"File is empty: {ctx.file_name}",
                parser_name=self.name,
                file_name=ctx.file_name,
                suggestion="Upload a non-empty file in a supported format.",
            )
        try:
            return self.parse(ctx)
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(
                f"Unexpected error parsing {ctx.file_name}: {exc}",
                parser_name=self.name,
                file_name=ctx.file_name,
                suggestion="The file may be corrupted or in an unsupported format. "
                           "Try re-exporting from the instrument software.",
                details={"original_error": type(exc).__name__, "message": str(exc)},
            ) from exc

    @abstractmethod
    def parse(self, ctx: FileContext) -> ParsedResult:
        """Parse instrument file bytes into canonical ParsedResult.

        Args:
            ctx: File context with bytes, name, and metadata.

        Returns:
            ParsedResult with measurements, settings, and warnings.

        Raises:
            ParseError: If file cannot be parsed (corrupted, wrong format, etc.)
        """

    @abstractmethod
    def can_handle(self, ctx: FileContext) -> bool:
        """Check whether this parser can handle the given file.

        Used by the parser auto-detection system. Implementations should
        check file extension, header patterns, and instrument_type hint.

        Args:
            ctx: File context to evaluate.

        Returns:
            True if this parser is likely able to parse the file.
        """

    def _make_result(
        self,
        ctx: FileContext,
        *,
        measurements: list | None = None,
        instrument_settings: InstrumentSettings | None = None,
        warnings: list[str] | None = None,
        raw_metadata: dict[str, Any] | None = None,
    ) -> ParsedResult:
        """Helper to construct a ParsedResult with common fields pre-filled."""
        meas = measurements or []
        unique_samples = {m.sample_id for m in meas if m.sample_id}
        return ParsedResult(
            parser_name=self.name,
            parser_version=self.version,
            instrument_type=self.instrument_type,
            file_name=ctx.file_name,
            file_hash=ctx.file_hash,
            measurements=meas,
            sample_count=len(unique_samples),
            measurement_count=len(meas),
            instrument_settings=instrument_settings or InstrumentSettings(),
            warnings=warnings or [],
            raw_metadata=raw_metadata or {},
        )

    def _raise_parse_error(
        self,
        message: str,
        ctx: FileContext,
        *,
        suggestion: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Convenience to raise ParseError with parser context pre-filled."""
        raise ParseError(
            message,
            parser_name=self.name,
            file_name=ctx.file_name,
            suggestion=suggestion,
            details=details,
        )

    def _decode_text(self, data: bytes) -> str:
        """Decode bytes to string, trying common encodings."""
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        raise ParseError(
            "Unable to decode file content",
            suggestion="Ensure the file is a valid text file with UTF-8 or Latin-1 encoding.",
        )
