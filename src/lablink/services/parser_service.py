"""Parser service — parser selection, dispatch, ASM conversion, and validation.

Orchestrates the parsing pipeline:
1. Select parser by instrument_type hint or auto-detect from file content
2. Execute parser to produce canonical ParsedResult
3. Validate the result against canonical schema
4. Store ParsedData record linked to the Upload
5. Update Upload status (parsed / parse_failed)

Zero HTTP awareness — called by task layer or directly by upload endpoints.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lablink.models import ParsedData, Upload, UploadStatus
from lablink.parsers.base import BaseParser, ParseError
from lablink.parsers.registry import ParserRegistry
from lablink.schemas.canonical import ParsedResult
from lablink.services.upload_service import UploadService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service errors
# ---------------------------------------------------------------------------


class ParserServiceError(Exception):
    """Raised when the parser service encounters an error."""

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        self.message = message
        self.suggestion = suggestion or "Check the file format and try again."
        super().__init__(message)


class NoParserFoundError(ParserServiceError):
    """Raised when no suitable parser is found for the file."""

    def __init__(self, filename: str, instrument_type: str | None = None) -> None:
        hint = f" (hint: {instrument_type})" if instrument_type else ""
        super().__init__(
            message=f"No parser found for '{filename}'{hint}.",
            suggestion="Use list_parsers to see supported formats and instrument types.",
        )


class ValidationError(ParserServiceError):
    """Raised when parsed output fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.validation_errors = errors
        super().__init__(
            message=f"Parsed result validation failed: {'; '.join(errors)}",
            suggestion="The parser produced invalid output. Try a different parser or check file format.",
        )


# ---------------------------------------------------------------------------
# Parser service
# ---------------------------------------------------------------------------


class ParserService:
    """Selects, dispatches, and validates instrument file parsers.

    Usage::

        service = ParserService(db=session)
        parsed_result, parsed_data = await service.parse_upload(upload_id)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._upload_service = UploadService(db=db)

    # -- Parser selection --------------------------------------------------

    @staticmethod
    def select_parser(
        file_bytes: bytes,
        filename: str | None = None,
        instrument_type: str | None = None,
    ) -> BaseParser:
        """Select the best parser for the given file.

        Strategy:
        1. If instrument_type is provided, look it up directly in the registry.
        2. Fall back to auto-detection via confidence scoring.

        Args:
            file_bytes: Raw file content.
            filename: Original filename for extension-based detection.
            instrument_type: Explicit instrument type hint.

        Returns:
            An instantiated parser.

        Raises:
            NoParserFoundError: If no suitable parser is found.
        """
        # Ensure parsers are imported/registered
        _ensure_parsers_loaded()

        # Strategy 1: Direct lookup by instrument_type
        if instrument_type:
            parser_cls = ParserRegistry.get(instrument_type)
            if parser_cls is not None:
                return parser_cls()
            logger.warning(
                "No parser registered for instrument_type=%r, falling back to auto-detect",
                instrument_type,
            )

        # Strategy 2: Auto-detect via confidence scoring
        parser_cls = ParserRegistry.detect(file_bytes, filename)
        if parser_cls is not None:
            return parser_cls()

        raise NoParserFoundError(filename=filename or "<unknown>", instrument_type=instrument_type)

    @staticmethod
    def list_parsers() -> list[dict[str, Any]]:
        """Return metadata about all registered parsers.

        Returns:
            List of dicts with parser info (name, version, instrument_type, extensions).
        """
        _ensure_parsers_loaded()
        result = []
        for instrument_type, parser_cls in ParserRegistry.all().items():
            result.append({
                "name": parser_cls.name,
                "version": parser_cls.version,
                "instrument_type": instrument_type,
                "supported_extensions": parser_cls.supported_extensions,
            })
        return result

    # -- Parse execution ---------------------------------------------------

    @staticmethod
    def execute_parser(
        parser: BaseParser,
        file_bytes: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> ParsedResult:
        """Execute a parser and return the canonical result.

        Args:
            parser: Instantiated parser.
            file_bytes: Raw file content.
            metadata: Optional metadata dict passed to the parser.

        Returns:
            ParsedResult from the parser.

        Raises:
            ParseError: If the parser fails to process the file.
        """
        return parser.parse(file_bytes, metadata)

    # -- Validation --------------------------------------------------------

    @staticmethod
    def validate_result(result: ParsedResult) -> list[str]:
        """Validate a ParsedResult for completeness and consistency.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        if not result.parser_name:
            errors.append("parser_name is required")
        if not result.parser_version:
            errors.append("parser_version is required")
        if not result.instrument_type:
            errors.append("instrument_type is required")
        if not result.measurement_type:
            errors.append("measurement_type is required")
        if result.sample_count < 0:
            errors.append("sample_count must be non-negative")
        if not result.measurements:
            errors.append("measurements list is empty")

        # Validate individual measurements
        for i, m in enumerate(result.measurements):
            if not m.unit:
                errors.append(f"measurement[{i}].unit is required")
            if not m.measurement_type:
                errors.append(f"measurement[{i}].measurement_type is required")

        return errors

    # -- Storage -----------------------------------------------------------

    async def store_parsed_data(
        self,
        upload: Upload,
        result: ParsedResult,
    ) -> ParsedData:
        """Store a ParsedResult as a ParsedData DB record.

        Args:
            upload: The originating Upload.
            result: Validated canonical ParsedResult.

        Returns:
            The created ParsedData ORM instance.
        """
        # Build data summary
        data_summary: dict[str, Any] = {
            "parser_name": result.parser_name,
            "sample_count": result.sample_count,
            "measurement_type": result.measurement_type,
            "measurement_count": len(result.measurements),
            "warnings": result.warnings,
        }

        # Serialize measurements to dicts
        measurements_dicts = [m.model_dump(mode="json") for m in result.measurements]

        # Serialize instrument settings
        settings_dict = (
            result.instrument_settings.model_dump(mode="json")
            if result.instrument_settings
            else None
        )

        # Build metadata
        metadata: dict[str, Any] = {
            **result.run_metadata,
        }
        if result.plate_layout:
            metadata["plate_layout"] = result.plate_layout
        if result.raw_headers:
            metadata["raw_headers"] = result.raw_headers

        parsed_data = ParsedData(
            upload_id=upload.id,
            organization_id=upload.organization_id,
            instrument_type=result.instrument_type,
            parser_version=result.parser_version,
            measurement_type=result.measurement_type,
            sample_count=result.sample_count,
            data_summary=data_summary,
            measurements=measurements_dicts,
            instrument_settings=settings_dict,
            metadata_=metadata,
        )

        self.db.add(parsed_data)
        await self.db.flush()

        logger.info(
            "Stored ParsedData %s for upload %s (%d measurements)",
            parsed_data.id,
            upload.id,
            len(measurements_dicts),
        )

        return parsed_data

    # -- Full pipeline -----------------------------------------------------

    async def parse_upload(
        self,
        upload_id: uuid.UUID,
        *,
        instrument_type: str | None = None,
    ) -> tuple[ParsedResult, ParsedData]:
        """Full parse pipeline for an upload: select parser, parse, validate, store.

        Args:
            upload_id: UUID of the Upload to parse.
            instrument_type: Optional hint for parser selection.

        Returns:
            Tuple of (ParsedResult, ParsedData).

        Raises:
            ParserServiceError: If upload not found.
            NoParserFoundError: If no suitable parser found.
            ParseError: If parsing fails.
            ValidationError: If parsed output is invalid.
        """
        # 1. Load upload record
        upload = await self.db.get(Upload, upload_id)
        if upload is None:
            raise ParserServiceError(
                f"Upload {upload_id} not found.",
                suggestion="Use list_uploads to find valid upload IDs.",
            )

        # 2. Update status to parsing
        upload.status = UploadStatus.parsing
        await self.db.flush()

        try:
            # 3. Retrieve file bytes from storage
            storage = self._upload_service.storage
            file_bytes = await storage.get(upload.s3_key)

            # 4. Select parser
            effective_type = instrument_type or upload.instrument_type_detected
            parser = self.select_parser(
                file_bytes,
                filename=upload.filename,
                instrument_type=effective_type,
            )

            # 5. Execute parser
            metadata = {
                "filename": upload.filename,
                "upload_id": str(upload.id),
                "organization_id": str(upload.organization_id),
            }
            if effective_type:
                metadata["instrument_type"] = effective_type

            result = self.execute_parser(parser, file_bytes, metadata)

            # 6. Validate
            validation_errors = self.validate_result(result)
            if validation_errors:
                raise ValidationError(validation_errors)

            # 7. Store parsed data
            parsed_data = await self.store_parsed_data(upload, result)

            # 8. Update upload status to parsed
            upload.status = UploadStatus.parsed
            upload.parsed_at = datetime.now(timezone.utc)
            upload.parser_used = result.parser_name
            upload.instrument_type_detected = result.instrument_type
            upload.error_message = None
            await self.db.flush()

            logger.info(
                "Successfully parsed upload %s with %s (%d measurements)",
                upload_id,
                result.parser_name,
                len(result.measurements),
            )

            return result, parsed_data

        except (NoParserFoundError, ParseError, ValidationError) as exc:
            # Mark upload as failed
            upload.status = UploadStatus.parse_failed
            upload.error_message = str(exc)
            await self.db.flush()

            logger.warning("Parse failed for upload %s: %s", upload_id, exc)
            raise

        except Exception as exc:
            # Unexpected error — still mark as failed
            upload.status = UploadStatus.parse_failed
            upload.error_message = f"Unexpected error: {exc}"
            await self.db.flush()

            logger.exception("Unexpected error parsing upload %s", upload_id)
            raise ParserServiceError(
                f"Unexpected error during parsing: {exc}",
                suggestion="Check server logs for details.",
            ) from exc


# ---------------------------------------------------------------------------
# Parser loading helper
# ---------------------------------------------------------------------------

_parsers_loaded = False


def _ensure_parsers_loaded() -> None:
    """Import all parser modules so they register with ParserRegistry.

    This is called lazily on first use to avoid circular imports.
    """
    global _parsers_loaded
    if _parsers_loaded:
        return

    # Import known parser modules — each one registers itself via @ParserRegistry.register
    _modules = [
        "lablink.parsers.spectrophotometer",
        "lablink.parsers.plate_reader",
    ]

    import importlib

    for module_name in _modules:
        try:
            importlib.import_module(module_name)
            logger.debug("Loaded parser module: %s", module_name)
        except ImportError:
            logger.debug("Parser module not available: %s", module_name)

    _parsers_loaded = True
