"""Small, explicit parsing helpers for GTFS CSV primitive values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Final

from transit.domain.gtfs_time import GtfsTimeParseError, parse_gtfs_time
from transit.services.static_import.contracts import StaticImportError

GTFS_DATE_FORMAT: Final = "%Y%m%d"


def required_text(row: dict[str, str], field: str, filename: str, row_number: int) -> str:
    """Get a required text field or issue a row-addressable validation error."""
    value = row.get(field, "")
    if value:
        return value
    raise StaticImportError("missing_value", f"{field} is required.", filename, row_number)


def optional_int(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
    default: int | None = None,
) -> int | None:
    """Parse an optional integer without permitting malformed values."""
    value = row.get(field, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise StaticImportError(
            "invalid_integer", f"{field} must be an integer.", filename, row_number
        ) from error


def required_int(row: dict[str, str], field: str, filename: str, row_number: int) -> int:
    """Parse a required integer field."""
    result = optional_int(row, field, filename, row_number)
    if result is None:
        raise StaticImportError("missing_value", f"{field} is required.", filename, row_number)
    return result


def required_decimal(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
) -> Decimal:
    """Parse a finite decimal coordinate field."""
    value = required_text(row, field, filename, row_number)
    try:
        decimal = Decimal(value)
    except InvalidOperation as error:
        raise StaticImportError(
            "invalid_decimal", f"{field} must be numeric.", filename, row_number
        ) from error
    if not decimal.is_finite():
        raise StaticImportError("invalid_decimal", f"{field} must be finite.", filename, row_number)
    return decimal


def required_date(row: dict[str, str], field: str, filename: str, row_number: int) -> date:
    """Parse the GTFS basic ISO date syntax."""
    value = required_text(row, field, filename, row_number)
    try:
        return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}")
    except ValueError as error:
        raise StaticImportError(
            "invalid_date", f"{field} must use YYYYMMDD.", filename, row_number
        ) from error


def optional_gtfs_seconds(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
) -> int | None:
    """Preserve post-midnight GTFS time semantics as seconds since service-day start."""
    value = row.get(field, "")
    if not value:
        return None
    try:
        gtfs_time = parse_gtfs_time(value)
    except GtfsTimeParseError as error:
        raise StaticImportError("invalid_gtfs_time", str(error), filename, row_number) from error

    return (
        gtfs_time.day_offset * 86_400
        + gtfs_time.time_of_day.hour * 3_600
        + gtfs_time.time_of_day.minute * 60
        + gtfs_time.time_of_day.second
    )


def normalised_colour(value: str, filename: str, row_number: int) -> str:
    """Accept an optional six-digit GTFS colour without a CSS hash prefix."""
    colour = value.strip().upper()
    if not colour:
        return ""
    if len(colour) != 6 or any(character not in "0123456789ABCDEF" for character in colour):
        raise StaticImportError(
            "invalid_colour", "Route colours must be six hex digits.", filename, row_number
        )
    return colour
