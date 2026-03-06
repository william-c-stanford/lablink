"""Auto-detect instrument type from file content.

Multi-layer detection strategy (per roadmap):
1. Agent-provided instrument_type hint in metadata (highest priority)
2. File extension matching against registered parsers
3. File header / content analysis via each parser's `detect()` method
4. If uncertain, returns "unidentified" with ranked candidates

Usage:
    from lablink.parsers.detector import detect_instrument

    result = detect_instrument(file_bytes, filename="sample.csv")
    print(result.instrument_type)   # "spectrophotometer"
    print(result.confidence)        # 0.85
    print(result.parser_class)      # <class SpectrophotometerParser>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lablink.parsers.base import BaseParser


# Minimum confidence to accept a detection without a hint
_MIN_AUTO_CONFIDENCE = 0.3

# Minimum confidence to accept a hint-boosted detection
_MIN_HINT_CONFIDENCE = 0.1


@dataclass(frozen=True)
class DetectionCandidate:
    """A single parser candidate with its confidence score."""

    instrument_type: str
    parser_class: type[BaseParser]
    confidence: float
    source: str  # "hint", "content", "extension"


@dataclass(frozen=True)
class DetectionResult:
    """Result of instrument type auto-detection.

    Attributes:
        instrument_type: Detected instrument type, or "unidentified".
        confidence: Confidence score (0.0-1.0) for the best match.
        parser_class: The parser class to use, or None if unidentified.
        candidates: All candidates ranked by confidence (descending).
        source: How the detection was made ("hint", "content", "extension", "unidentified").
    """

    instrument_type: str
    confidence: float
    parser_class: type[BaseParser] | None
    candidates: list[DetectionCandidate] = field(default_factory=list)
    source: str = "unidentified"


def detect_instrument(
    file_bytes: bytes,
    filename: str | None = None,
    hint: str | None = None,
    metadata: dict | None = None,
) -> DetectionResult:
    """Auto-detect instrument type from file content using multi-layer strategy.

    Detection layers (in priority order):
    1. **Hint** — If `hint` or `metadata["instrument_type"]` is provided and matches
       a registered parser, use it (boosted confidence). The parser's `detect()` is
       still called to validate; if it scores > 0, the hint is accepted.
    2. **Content analysis** — Each registered parser's `detect()` method scores the
       file. The highest-scoring parser wins if above the minimum threshold.
    3. **Unidentified** — If no parser scores above threshold, return "unidentified"
       with ranked candidates so the caller can prompt the user.

    Args:
        file_bytes: Raw file content bytes.
        filename: Original filename (used for extension matching).
        hint: Explicit instrument_type hint (e.g., from agent metadata).
        metadata: Optional metadata dict; `metadata["instrument_type"]` is used as
                  a hint if `hint` is not provided.

    Returns:
        DetectionResult with the best match and ranked candidates.
    """
    from lablink.parsers.registry import ParserRegistry

    # Resolve hint from metadata if not explicitly provided
    effective_hint = hint
    if not effective_hint and metadata:
        effective_hint = metadata.get("instrument_type")

    # Score all registered parsers
    all_parsers = ParserRegistry.all()
    if not all_parsers:
        return DetectionResult(
            instrument_type="unidentified",
            confidence=0.0,
            parser_class=None,
            candidates=[],
            source="unidentified",
        )

    candidates: list[DetectionCandidate] = []

    for instrument_type, parser_class in all_parsers.items():
        try:
            parser = parser_class()
            score = parser.detect(file_bytes, filename)
        except Exception:
            score = 0.0

        if score > 0.0:
            candidates.append(
                DetectionCandidate(
                    instrument_type=instrument_type,
                    parser_class=parser_class,
                    confidence=score,
                    source="content" if score > 0.5 else "extension",
                )
            )

    # Sort by confidence descending
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    # Layer 1: Hint-based detection
    if effective_hint:
        # Check if hint matches a registered parser
        hint_parser = ParserRegistry.get(effective_hint)
        if hint_parser is not None:
            # Find the hint parser's score in candidates
            hint_score = 0.0
            for c in candidates:
                if c.instrument_type == effective_hint:
                    hint_score = c.confidence
                    break

            # If the hinted parser scored anything, or even if it didn't score
            # but exists, accept it (agent knows best)
            if hint_score >= _MIN_HINT_CONFIDENCE:
                return DetectionResult(
                    instrument_type=effective_hint,
                    confidence=max(hint_score, 0.6),  # Boost hint confidence floor
                    parser_class=hint_parser,
                    candidates=candidates,
                    source="hint",
                )
            else:
                # Hint exists but parser didn't detect the file — still trust the hint
                # but with lower confidence
                try:
                    parser = hint_parser()
                    score = parser.detect(file_bytes, filename)
                except Exception:
                    score = 0.0

                # Even with 0 score, if a valid hint was provided, trust it
                return DetectionResult(
                    instrument_type=effective_hint,
                    confidence=max(score, 0.4),
                    parser_class=hint_parser,
                    candidates=candidates,
                    source="hint",
                )

    # Layer 2: Content-based detection (best scoring parser)
    if candidates and candidates[0].confidence >= _MIN_AUTO_CONFIDENCE:
        best = candidates[0]

        # Check for ambiguity: if top two are very close, flag it
        if (
            len(candidates) >= 2
            and candidates[1].confidence > 0.0
            and (candidates[0].confidence - candidates[1].confidence) < 0.05
        ):
            # Ambiguous — still return best but note it
            return DetectionResult(
                instrument_type=best.instrument_type,
                confidence=best.confidence,
                parser_class=best.parser_class,
                candidates=candidates,
                source="content",
            )

        return DetectionResult(
            instrument_type=best.instrument_type,
            confidence=best.confidence,
            parser_class=best.parser_class,
            candidates=candidates,
            source="content",
        )

    # Layer 3: Unidentified
    return DetectionResult(
        instrument_type="unidentified",
        confidence=0.0,
        parser_class=None,
        candidates=candidates,
        source="unidentified",
    )


def detect_instrument_type(
    file_bytes: bytes,
    filename: str | None = None,
    hint: str | None = None,
) -> tuple[str | None, float]:
    """Simple detection interface returning (instrument_type, confidence_score).

    Uses hint first (if provided), then ParserRegistry.detect(), then
    extension-based fallback.

    Args:
        file_bytes: Raw file content bytes.
        filename: Original filename for extension matching.
        hint: Explicit instrument_type hint from caller.

    Returns:
        Tuple of (instrument_type or None, confidence_score 0.0-1.0).
    """
    result = detect_instrument(file_bytes, filename=filename, hint=hint)
    if result.instrument_type == "unidentified":
        return None, 0.0
    return result.instrument_type, result.confidence


def detect_and_parse(
    file_bytes: bytes,
    filename: str | None = None,
    hint: str | None = None,
    metadata: dict | None = None,
) -> tuple[DetectionResult, "ParsedResult | None"]:
    """Detect instrument type and parse in one step.

    Convenience function that detects the instrument type and immediately
    parses the file if a parser is found.

    Args:
        file_bytes: Raw file content bytes.
        filename: Original filename.
        hint: Explicit instrument_type hint.
        metadata: Optional metadata dict.

    Returns:
        Tuple of (DetectionResult, ParsedResult or None).
        ParsedResult is None if detection failed or parsing raised an error.
    """
    from lablink.parsers.base import ParseError
    from lablink.schemas.canonical import ParsedResult

    detection = detect_instrument(file_bytes, filename, hint, metadata)

    if detection.parser_class is None:
        return detection, None

    try:
        parser = detection.parser_class()
        parsed = parser.parse(file_bytes, metadata)
        return detection, parsed
    except ParseError:
        return detection, None
    except Exception:
        return detection, None
