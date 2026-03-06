"""Instrument file parsers for LabLink."""

from app.parsers.base import BaseParser, FileContext, ParseError
from app.parsers.spectrophotometer import SpectrophotometerParser
from app.parsers.plate_reader import PlateReaderParser
from app.parsers.hplc import HPLCParser
from app.parsers.pcr import PCRParser
from app.parsers.balance import BalanceParser
from app.schemas.parsed_result import (
    InstrumentSettings,
    MeasurementValue,
    ParsedResult,
    QualityFlag,
)

PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "spectrophotometer": SpectrophotometerParser,
    "plate_reader": PlateReaderParser,
    "hplc": HPLCParser,
    "pcr": PCRParser,
    "balance": BalanceParser,
}

__all__ = [
    "BaseParser",
    "BalanceParser",
    "FileContext",
    "HPLCParser",
    "InstrumentSettings",
    "MeasurementValue",
    "PARSER_REGISTRY",
    "PCRParser",
    "ParseError",
    "ParsedResult",
    "PlateReaderParser",
    "QualityFlag",
    "SpectrophotometerParser",
]
