"""GTFS schedule time parsing with explicit after-midnight support."""

import re
from dataclasses import dataclass
from datetime import time
from typing import Final

_GTFS_TIME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})$"
)
_MAX_GTFS_HOUR: Final = 47


@dataclass(frozen=True, slots=True)
class GtfsTime:
    """A GTFS time retaining the service-day offset implied by its hour."""

    raw_value: str
    day_offset: int
    time_of_day: time


@dataclass(frozen=True, slots=True)
class GtfsTimeParseError(Exception):
    """Raised when a GTFS time cannot represent a valid service-day time."""

    raw_value: str
    reason: str

    def __str__(self) -> str:
        """Return the invalid GTFS value and the specific validation reason."""
        return f"invalid GTFS time {self.raw_value!r}: {self.reason}"


def parse_gtfs_time(raw_value: str) -> GtfsTime:
    """Parse an HH:MM:SS GTFS value, including valid times after midnight."""
    matched_time = _GTFS_TIME_PATTERN.fullmatch(raw_value)
    if matched_time is None:
        raise GtfsTimeParseError(raw_value=raw_value, reason="expected HH:MM:SS")

    hour = int(matched_time.group("hour"))
    minute = int(matched_time.group("minute"))
    second = int(matched_time.group("second"))
    if hour > _MAX_GTFS_HOUR or minute > 59 or second > 59:
        raise GtfsTimeParseError(raw_value=raw_value, reason="component outside GTFS range")

    return GtfsTime(
        raw_value=raw_value,
        day_offset=hour // 24,
        time_of_day=time(hour=hour % 24, minute=minute, second=second),
    )
