"""Resolve versioned trip geometry with explicit quality and provenance."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

from transit.models import GtfsShapePoint, GtfsTrip, StaticFeedVersion

GeometryQuality = Literal[
    "official_shape",
    "matched_infrastructure",
    "stop_sequence",
    "unavailable",
]
GeometrySource = Literal["gtfs", "derived_infrastructure", "scheduled_stops", "none"]
Coordinate = tuple[float, float]

_EARTH_RADIUS_METRES: Final = 6_371_008.8
_MAX_ENDPOINT_DISTANCE_METRES: Final = 2_000.0


@dataclass(frozen=True, slots=True)
class ResolvedTripGeometry:
    """A route line whose quality and provenance survive API serialization."""

    coordinates: tuple[Coordinate, ...] | None
    quality: GeometryQuality
    shape_id: str | None
    source: GeometrySource
    source_version: str
    attribution: str | None = None


def resolve_trip_geometry(
    version: StaticFeedVersion,
    trip: GtfsTrip,
    scheduled_stops: tuple[Coordinate, ...],
    matched_infrastructure: ResolvedTripGeometry | None = None,
) -> ResolvedTripGeometry:
    """Prefer an aligned official shape, then expose an honest stop-sequence fallback."""
    version_id = str(version.id)
    stop_coordinates = _distinct_coordinates(scheduled_stops)
    if trip.shape_id:
        shape_coordinates = _distinct_coordinates(
            tuple(
                (float(longitude), float(latitude))
                for longitude, latitude in GtfsShapePoint.objects.filter(
                    feed_version=version,
                    shape_id=trip.shape_id,
                )
                .order_by("sequence")
                .values_list("longitude", "latitude")
            )
        )
        if _shape_covers_terminal_stops(shape_coordinates, stop_coordinates):
            return ResolvedTripGeometry(
                coordinates=shape_coordinates,
                quality="official_shape",
                shape_id=trip.shape_id,
                source="gtfs",
                source_version=version_id,
            )
    if _valid_matched_infrastructure(matched_infrastructure, version_id):
        return matched_infrastructure
    if len(stop_coordinates) >= 2:
        return ResolvedTripGeometry(
            coordinates=stop_coordinates,
            quality="stop_sequence",
            shape_id=None,
            source="scheduled_stops",
            source_version=version_id,
        )
    return ResolvedTripGeometry(
        coordinates=None,
        quality="unavailable",
        shape_id=None,
        source="none",
        source_version=version_id,
    )


def _valid_matched_infrastructure(
    geometry: ResolvedTripGeometry | None,
    version_id: str,
) -> bool:
    return bool(
        geometry
        and geometry.quality == "matched_infrastructure"
        and geometry.source == "derived_infrastructure"
        and geometry.source_version == version_id
        and geometry.shape_id is None
        and geometry.attribution
        and geometry.coordinates
        and len(_distinct_coordinates(geometry.coordinates)) >= 2
    )


def _distinct_coordinates(coordinates: tuple[Coordinate, ...]) -> tuple[Coordinate, ...]:
    distinct: list[Coordinate] = []
    for coordinate in coordinates:
        if not distinct or distinct[-1] != coordinate:
            distinct.append(coordinate)
    return tuple(distinct)


def _shape_covers_terminal_stops(
    shape_coordinates: tuple[Coordinate, ...],
    stop_coordinates: tuple[Coordinate, ...],
) -> bool:
    if len(shape_coordinates) < 2 or len(stop_coordinates) < 2:
        return False
    return all(
        _distance_to_polyline_metres(stop, shape_coordinates) <= _MAX_ENDPOINT_DISTANCE_METRES
        for stop in (stop_coordinates[0], stop_coordinates[-1])
    )


def _distance_to_polyline_metres(point: Coordinate, line: tuple[Coordinate, ...]) -> float:
    return min(
        _point_to_segment_metres(point, start, end)
        for start, end in pairwise(line)
    )


def _point_to_segment_metres(
    point: Coordinate,
    segment_start: Coordinate,
    segment_end: Coordinate,
) -> float:
    longitude, latitude = point
    latitude_radians = math.radians(latitude)

    def local_metres(coordinate: Coordinate) -> Coordinate:
        coordinate_longitude, coordinate_latitude = coordinate
        return (
            math.radians(coordinate_longitude - longitude)
            * math.cos(latitude_radians)
            * _EARTH_RADIUS_METRES,
            math.radians(coordinate_latitude - latitude) * _EARTH_RADIUS_METRES,
        )

    start_x, start_y = local_metres(segment_start)
    end_x, end_y = local_metres(segment_end)
    segment_x = end_x - start_x
    segment_y = end_y - start_y
    squared_length = segment_x * segment_x + segment_y * segment_y
    if squared_length == 0:
        return math.hypot(start_x, start_y)
    projection = max(
        0.0,
        min(1.0, -(start_x * segment_x + start_y * segment_y) / squared_length),
    )
    return math.hypot(start_x + projection * segment_x, start_y + projection * segment_y)
