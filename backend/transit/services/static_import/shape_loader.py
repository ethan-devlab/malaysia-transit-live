"""Load optional GTFS shape points into an immutable static-feed version."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from decimal import Decimal

from transit.models import GtfsShapePoint, GtfsTrip, StaticFeedVersion
from transit.services.static_import.archive import has_member, iter_rows
from transit.services.static_import.contracts import StaticImportError
from transit.services.static_import.parsing import required_decimal, required_int, required_text

BATCH_SIZE = 1_000
MAX_POINTS_PER_SHAPE = 50_000


@dataclass(frozen=True, slots=True)
class ShapeImportSummary:
    """Counts produced while loading shape points and comparing trip references."""

    distinct_shape_count: int
    point_count: int
    trips_with_shape_count: int
    trips_without_shape_count: int
    orphan_trip_shape_count: int


def load_shapes(archive: zipfile.ZipFile, version: StaticFeedVersion) -> ShapeImportSummary:
    """Load optional ``shapes.txt`` rows and report trip-shape coverage."""
    imported_shape_ids: set[str] = set()
    point_count = 0
    if has_member(archive, "shapes.txt"):
        point_count, imported_shape_ids = _load_shape_points(archive, version)

    trip_shape_ids = tuple(
        GtfsTrip.objects.filter(feed_version=version)
        .exclude(shape_id="")
        .values_list("shape_id", flat=True)
    )
    return ShapeImportSummary(
        distinct_shape_count=len(imported_shape_ids),
        point_count=point_count,
        trips_with_shape_count=len(trip_shape_ids),
        trips_without_shape_count=GtfsTrip.objects.filter(
            feed_version=version,
            shape_id="",
        ).count(),
        orphan_trip_shape_count=sum(
            shape_id not in imported_shape_ids for shape_id in trip_shape_ids
        ),
    )


def _load_shape_points(
    archive: zipfile.ZipFile,
    version: StaticFeedVersion,
) -> tuple[int, set[str]]:
    filename = "shapes.txt"
    points: list[GtfsShapePoint] = []
    seen_points: set[tuple[str, int]] = set()
    shape_point_counts: dict[str, int] = {}
    distances_by_shape: dict[str, list[tuple[int, Decimal, int]]] = {}
    imported_shape_ids: set[str] = set()
    point_count = 0

    for row_number, row in iter_rows(
        archive,
        filename,
        ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"),
    ):
        shape_id = required_text(row, "shape_id", filename, row_number)
        sequence = required_int(row, "shape_pt_sequence", filename, row_number)
        if sequence < 0:
            raise StaticImportError(
                "invalid_sequence",
                "shape_pt_sequence cannot be negative.",
                filename,
                row_number,
            )
        point_key = (shape_id, sequence)
        if point_key in seen_points:
            raise StaticImportError(
                "duplicate_identifier",
                f"Duplicate shape_id and shape_pt_sequence: {shape_id}, {sequence}.",
                filename,
                row_number,
            )
        seen_points.add(point_key)

        shape_point_count = shape_point_counts.get(shape_id, 0) + 1
        if shape_point_count > MAX_POINTS_PER_SHAPE:
            raise StaticImportError(
                "shape_too_large",
                f"Shape {shape_id} exceeds {MAX_POINTS_PER_SHAPE} points.",
                filename,
                row_number,
            )
        shape_point_counts[shape_id] = shape_point_count

        latitude = required_decimal(row, "shape_pt_lat", filename, row_number)
        longitude = required_decimal(row, "shape_pt_lon", filename, row_number)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise StaticImportError(
                "invalid_coordinate",
                "Shape coordinates are out of range.",
                filename,
                row_number,
            )

        distance_travelled = _optional_distance(row, filename, row_number)
        if distance_travelled is not None:
            distances_by_shape.setdefault(shape_id, []).append(
                (sequence, distance_travelled, row_number)
            )

        imported_shape_ids.add(shape_id)
        points.append(
            GtfsShapePoint(
                feed_version=version,
                shape_id=shape_id,
                sequence=sequence,
                latitude=latitude,
                longitude=longitude,
                distance_travelled=distance_travelled,
            )
        )
        point_count += 1
        if len(points) >= BATCH_SIZE:
            GtfsShapePoint.objects.bulk_create(points, batch_size=BATCH_SIZE)
            points.clear()

    _validate_shape_distances(distances_by_shape, filename)
    if points:
        GtfsShapePoint.objects.bulk_create(points, batch_size=BATCH_SIZE)
    return point_count, imported_shape_ids


def _validate_shape_distances(
    distances_by_shape: dict[str, list[tuple[int, Decimal, int]]],
    filename: str,
) -> None:
    for values in distances_by_shape.values():
        previous_distance: Decimal | None = None
        for _, distance, row_number in sorted(values):
            if previous_distance is not None and distance < previous_distance:
                raise StaticImportError(
                    "invalid_distance",
                    "shape_dist_traveled must be non-decreasing by shape_pt_sequence.",
                    filename,
                    row_number,
                )
            previous_distance = distance


def _optional_distance(
    row: dict[str, str],
    filename: str,
    row_number: int,
) -> Decimal | None:
    if not row.get("shape_dist_traveled", ""):
        return None
    distance = required_decimal(row, "shape_dist_traveled", filename, row_number)
    if distance < 0:
        raise StaticImportError(
            "invalid_distance",
            "shape_dist_traveled cannot be negative.",
            filename,
            row_number,
        )
    return distance
