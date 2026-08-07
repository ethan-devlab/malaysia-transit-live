"""Load GTFS service calendars, trips, and ordered stop times."""

from __future__ import annotations

import zipfile
from datetime import date

from transit.models import (
    GtfsRoute,
    GtfsService,
    GtfsServiceException,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    StaticFeedVersion,
)
from transit.services.static_import.archive import has_member, iter_rows
from transit.services.static_import.contracts import StaticImportError
from transit.services.static_import.parsing import (
    optional_gtfs_seconds,
    optional_int,
    required_date,
    required_int,
    required_text,
)

BATCH_SIZE = 1_000
DAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def load_services(archive: zipfile.ZipFile, version: StaticFeedVersion) -> tuple[int, int]:
    """Load calendar and exception-only service definitions when either file exists."""
    calendar_exists = has_member(archive, "calendar.txt")
    exceptions_exist = has_member(archive, "calendar_dates.txt")
    if not calendar_exists and not exceptions_exist:
        raise StaticImportError(
            "missing_service_calendar",
            "Either calendar.txt or calendar_dates.txt is required.",
            "archive",
        )

    service_count = _load_calendar(archive, version) if calendar_exists else 0
    exception_count = _load_service_exceptions(archive, version) if exceptions_exist else 0
    return service_count, exception_count


def load_trips(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    """Load trips only after their route and service references have been validated."""
    filename = "trips.txt"
    route_ids = set(
        GtfsRoute.objects.filter(feed_version=version).values_list("route_id", flat=True)
    )
    service_ids = set(
        GtfsService.objects.filter(feed_version=version).values_list("service_id", flat=True)
    )
    trips: list[GtfsTrip] = []
    trip_ids: set[str] = set()
    for row_number, row in iter_rows(archive, filename, ("route_id", "service_id", "trip_id")):
        route_id = required_text(row, "route_id", filename, row_number)
        service_id = required_text(row, "service_id", filename, row_number)
        trip_id = required_text(row, "trip_id", filename, row_number)
        _require_reference(route_id, route_ids, "route_id", filename, row_number)
        _require_reference(service_id, service_ids, "service_id", filename, row_number)
        _require_unique(trip_id, trip_ids, "trip_id", filename, row_number)
        trips.append(
            GtfsTrip(
                feed_version=version,
                trip_id=trip_id,
                route_id=route_id,
                service_id=service_id,
                headsign=row.get("trip_headsign", ""),
                short_name=row.get("trip_short_name", ""),
                direction_id=_binary_or_none(row, "direction_id", filename, row_number),
                block_id=row.get("block_id", ""),
                shape_id=row.get("shape_id", ""),
                wheelchair_accessible=_nonnegative_or_default(
                    row,
                    "wheelchair_accessible",
                    filename,
                    row_number,
                    0,
                ),
                bikes_allowed=_nonnegative_or_default(
                    row,
                    "bikes_allowed",
                    filename,
                    row_number,
                    0,
                ),
            )
        )
    _bulk_insert(trips)
    return len(trips)


def load_stop_times(archive: zipfile.ZipFile, version: StaticFeedVersion) -> tuple[int, int]:
    """Load stop times and count records whose optional stop reference is absent."""
    filename = "stop_times.txt"
    trip_ids = dict(GtfsTrip.objects.filter(feed_version=version).values_list("trip_id", "id"))
    stop_ids = set(GtfsStop.objects.filter(feed_version=version).values_list("stop_id", flat=True))
    stop_times: list[GtfsStopTime] = []
    orphan_stop_time_count = 0
    trip_sequences: set[tuple[str, int]] = set()
    for row_number, row in iter_rows(archive, filename, ("trip_id", "stop_id", "stop_sequence")):
        trip_id = required_text(row, "trip_id", filename, row_number)
        stop_id = required_text(row, "stop_id", filename, row_number)
        sequence = required_int(row, "stop_sequence", filename, row_number)
        if sequence < 0:
            raise StaticImportError(
                "invalid_sequence", "stop_sequence cannot be negative.", filename, row_number
            )
        _require_reference(trip_id, set(trip_ids), "trip_id", filename, row_number)
        if stop_id not in stop_ids:
            orphan_stop_time_count += 1
        _require_unique(
            (trip_id, sequence), trip_sequences, "trip_id and stop_sequence", filename, row_number
        )
        arrival_time = row.get("arrival_time", "")
        departure_time = row.get("departure_time", "")
        stop_times.append(
            GtfsStopTime(
                trip_id=trip_ids[trip_id],
                stop_id=stop_id,
                stop_sequence=sequence,
                arrival_time=arrival_time,
                departure_time=departure_time,
                arrival_seconds=optional_gtfs_seconds(row, "arrival_time", filename, row_number),
                departure_seconds=optional_gtfs_seconds(
                    row,
                    "departure_time",
                    filename,
                    row_number,
                ),
                stop_headsign=row.get("stop_headsign", ""),
                pickup_type=_nonnegative_or_default(row, "pickup_type", filename, row_number, 0),
                drop_off_type=_nonnegative_or_default(
                    row,
                    "drop_off_type",
                    filename,
                    row_number,
                    0,
                ),
                timepoint=_nonnegative_or_default(row, "timepoint", filename, row_number, 1),
            )
        )
    _bulk_insert(stop_times)
    return len(stop_times), orphan_stop_time_count


def _load_calendar(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    filename = "calendar.txt"
    services: list[GtfsService] = []
    service_ids: set[str] = set()
    required_columns = ("service_id", *DAY_FIELDS, "start_date", "end_date")
    for row_number, row in iter_rows(archive, filename, required_columns):
        service_id = required_text(row, "service_id", filename, row_number)
        _require_unique(service_id, service_ids, "service_id", filename, row_number)
        weekday_values = {
            day: _binary_or_default(row, day, filename, row_number) for day in DAY_FIELDS
        }
        start_date = required_date(row, "start_date", filename, row_number)
        end_date = required_date(row, "end_date", filename, row_number)
        if end_date < start_date:
            raise StaticImportError(
                "invalid_date_range", "end_date precedes start_date.", filename, row_number
            )
        services.append(
            GtfsService(
                feed_version=version,
                service_id=service_id,
                start_date=start_date,
                end_date=end_date,
                **weekday_values,
            )
        )
    _bulk_insert(services)
    return len(services)


def _load_service_exceptions(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    filename = "calendar_dates.txt"
    service_ids = dict(
        GtfsService.objects.filter(feed_version=version).values_list("service_id", "id")
    )
    exceptions: list[GtfsServiceException] = []
    unique_exceptions: set[tuple[str, date]] = set()
    for row_number, row in iter_rows(archive, filename, ("service_id", "date", "exception_type")):
        service_id = required_text(row, "service_id", filename, row_number)
        if service_id not in service_ids:
            service = GtfsService.objects.create(feed_version=version, service_id=service_id)
            service_ids[service_id] = service.id
        service_date = required_date(row, "date", filename, row_number)
        exception_type = required_int(row, "exception_type", filename, row_number)
        if exception_type not in {1, 2}:
            raise StaticImportError(
                "invalid_exception_type",
                "exception_type must be 1 or 2.",
                filename,
                row_number,
            )
        _require_unique(
            (service_id, service_date),
            unique_exceptions,
            "service_id and date",
            filename,
            row_number,
        )
        exceptions.append(
            GtfsServiceException(
                service_id=service_ids[service_id],
                service_date=service_date,
                exception_type=exception_type,
            )
        )
    _bulk_insert(exceptions)
    return len(exceptions)


def _bulk_insert(
    records: list[GtfsService] | list[GtfsServiceException] | list[GtfsStopTime] | list[GtfsTrip],
) -> None:
    for index in range(0, len(records), BATCH_SIZE):
        batch = records[index : index + BATCH_SIZE]
        if batch:
            batch[0].__class__.objects.bulk_create(batch, batch_size=BATCH_SIZE)


def _binary_or_default(row: dict[str, str], field: str, filename: str, row_number: int) -> bool:
    value = _nonnegative_or_default(row, field, filename, row_number, 0)
    if value not in {0, 1}:
        raise StaticImportError("invalid_binary", f"{field} must be 0 or 1.", filename, row_number)
    return value == 1


def _binary_or_none(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
) -> int | None:
    value = optional_int(row, field, filename, row_number)
    if value is None:
        return None
    if value not in {0, 1}:
        raise StaticImportError("invalid_binary", f"{field} must be 0 or 1.", filename, row_number)
    return value


def _nonnegative_or_default(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
    default: int,
) -> int:
    value = optional_int(row, field, filename, row_number, default)
    if value is None or value < 0:
        raise StaticImportError(
            "invalid_integer", f"{field} must be non-negative.", filename, row_number
        )
    return value


def _require_reference(
    value: str,
    known_values: set[str],
    field: str,
    filename: str,
    row_number: int,
) -> None:
    if value not in known_values:
        raise StaticImportError(
            "orphan_reference", f"Unknown {field}: {value}.", filename, row_number
        )


def _require_unique(
    value: object,
    known_values: set[object],
    field: str,
    filename: str,
    row_number: int,
) -> None:
    if value in known_values:
        raise StaticImportError(
            "duplicate_identifier", f"Duplicate {field}: {value}.", filename, row_number
        )
    known_values.add(value)
