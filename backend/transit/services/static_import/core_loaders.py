"""Load agencies, routes, and stops into a staged GTFS version."""

from __future__ import annotations

import zipfile

from transit.models import GtfsAgency, GtfsRoute, GtfsStop, StaticFeedVersion
from transit.services.static_import.archive import iter_rows
from transit.services.static_import.contracts import StaticImportError
from transit.services.static_import.parsing import (
    normalised_colour,
    optional_int,
    required_decimal,
    required_int,
    required_text,
)

BATCH_SIZE = 1_000


def load_agencies(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    """Load agency records, treating a missing single-agency identifier as stable."""
    filename = "agency.txt"
    agencies: list[GtfsAgency] = []
    agency_ids: set[str] = set()
    for row_number, row in iter_rows(
        archive, filename, ("agency_name", "agency_url", "agency_timezone")
    ):
        agency_id = row.get("agency_id", "") or "__default__"
        _require_unique(agency_id, agency_ids, filename, row_number, "agency_id")
        agencies.append(
            GtfsAgency(
                feed_version=version,
                agency_id=agency_id,
                name=required_text(row, "agency_name", filename, row_number),
                url=required_text(row, "agency_url", filename, row_number),
                timezone=required_text(row, "agency_timezone", filename, row_number),
                language=row.get("agency_lang", ""),
                phone=row.get("agency_phone", ""),
            )
        )
    _bulk_insert(agencies)
    return len(agencies)


def load_routes(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    """Load routes and their display metadata."""
    filename = "routes.txt"
    routes: list[GtfsRoute] = []
    route_ids: set[str] = set()
    for row_number, row in iter_rows(archive, filename, ("route_id", "route_type")):
        route_id = required_text(row, "route_id", filename, row_number)
        _require_unique(route_id, route_ids, filename, row_number, "route_id")
        route_type = required_int(row, "route_type", filename, row_number)
        if route_type < 0:
            raise StaticImportError(
                "invalid_route_type", "route_type cannot be negative.", filename, row_number
            )
        routes.append(
            GtfsRoute(
                feed_version=version,
                route_id=route_id,
                agency_id=row.get("agency_id", ""),
                short_name=row.get("route_short_name", ""),
                long_name=row.get("route_long_name", ""),
                description=row.get("route_desc", ""),
                route_type=route_type,
                route_color=normalised_colour(row.get("route_color", ""), filename, row_number),
                text_color=normalised_colour(row.get("route_text_color", ""), filename, row_number),
                sort_order=optional_int(row, "route_sort_order", filename, row_number),
            )
        )
    _bulk_insert(routes)
    return len(routes)


def load_stops(archive: zipfile.ZipFile, version: StaticFeedVersion) -> int:
    """Load stops with bounded geographic coordinates for nearby-stop queries."""
    filename = "stops.txt"
    stops: list[GtfsStop] = []
    stop_ids: set[str] = set()
    for row_number, row in iter_rows(
        archive, filename, ("stop_id", "stop_name", "stop_lat", "stop_lon")
    ):
        stop_id = required_text(row, "stop_id", filename, row_number)
        _require_unique(stop_id, stop_ids, filename, row_number, "stop_id")
        latitude = required_decimal(row, "stop_lat", filename, row_number)
        longitude = required_decimal(row, "stop_lon", filename, row_number)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise StaticImportError(
                "invalid_coordinate", "Stop coordinates are out of range.", filename, row_number
            )
        stops.append(
            GtfsStop(
                feed_version=version,
                stop_id=stop_id,
                name=required_text(row, "stop_name", filename, row_number),
                description=row.get("stop_desc", ""),
                latitude=latitude,
                longitude=longitude,
                location_type=_nonnegative_int(row, "location_type", filename, row_number, 0),
                parent_station_id=row.get("parent_station", ""),
                platform_code=row.get("platform_code", ""),
                wheelchair_boarding=_nonnegative_int(
                    row,
                    "wheelchair_boarding",
                    filename,
                    row_number,
                    0,
                ),
            )
        )
    _bulk_insert(stops)
    return len(stops)


def _bulk_insert(records: list[GtfsAgency] | list[GtfsRoute] | list[GtfsStop]) -> None:
    for index in range(0, len(records), BATCH_SIZE):
        batch = records[index : index + BATCH_SIZE]
        if batch:
            batch[0].__class__.objects.bulk_create(batch, batch_size=BATCH_SIZE)


def _nonnegative_int(
    row: dict[str, str],
    field: str,
    filename: str,
    row_number: int,
    default: int,
) -> int:
    result = optional_int(row, field, filename, row_number, default)
    if result is None or result < 0:
        raise StaticImportError(
            "invalid_integer", f"{field} must be non-negative.", filename, row_number
        )
    return result


def _require_unique(
    value: str,
    known_values: set[str],
    filename: str,
    row_number: int,
    field: str,
) -> None:
    if value in known_values:
        raise StaticImportError(
            "duplicate_identifier", f"Duplicate {field}: {value}.", filename, row_number
        )
    known_values.add(value)
