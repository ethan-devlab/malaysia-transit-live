from datetime import time

import pytest

from transit.domain.gtfs_time import GtfsTimeParseError, parse_gtfs_time


def test_parse_gtfs_time_when_after_midnight_preserves_day_offset() -> None:
    # Given
    raw_time = "25:15:00"

    # When
    parsed_time = parse_gtfs_time(raw_time)

    # Then
    assert parsed_time.day_offset == 1
    assert parsed_time.time_of_day == time(hour=1, minute=15)
    assert parsed_time.raw_value == raw_time


@pytest.mark.parametrize("raw_time", ["24:60:00", "-01:00:00", "not-a-time"])
def test_parse_gtfs_time_when_invalid_raises_typed_error(raw_time: str) -> None:
    # Given
    invalid_value = raw_time

    # When / Then
    with pytest.raises(GtfsTimeParseError):
        parse_gtfs_time(invalid_value)
