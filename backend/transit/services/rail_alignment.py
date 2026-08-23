"""Persist deterministic KTMB matching outputs and bounded review artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transit.models import (
    DerivedTripAlignment,
    GtfsShapePoint,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    RailInfrastructureSnapshot,
    StaticFeedVersion,
)
from transit.services.rail_infrastructure import railway_graph, refresh_geometry_coverage
from transit.services.rail_matching import (
    DERIVATION_VERSION,
    PathCache,
    match_ordered_stops,
    matcher_configuration,
)


@dataclass(frozen=True, slots=True)
class AlignmentDerivationRun:
    """Describe one idempotent versioned matcher run for report generation."""

    alignments: tuple[DerivedTripAlignment, ...]
    matcher_config_sha256: str
    reused_count: int


def derive_alignments(
    version: StaticFeedVersion,
    snapshot: RailInfrastructureSnapshot,
) -> AlignmentDerivationRun:
    """Match only trips lacking imported GTFS shape points and persist each outcome."""
    if snapshot.status != RailInfrastructureSnapshot.Status.IMPORTED:
        raise ValueError("Only an imported infrastructure snapshot can be matched.")
    config_sha256 = _matcher_config_sha256()
    graph = railway_graph(snapshot)
    trips = _eligible_trips(version)
    stops_by_trip = _stops_by_trip(trips)
    path_cache: PathCache = {}
    existing = {
        alignment.trip_id: alignment
        for alignment in DerivedTripAlignment.objects.filter(
            derivation_version=DERIVATION_VERSION,
            matcher_config_sha256=config_sha256,
            snapshot=snapshot,
            static_feed_version=version,
            trip__in=trips,
        ).select_related("trip")
    }
    created: list[DerivedTripAlignment] = []
    alignments: list[DerivedTripAlignment] = []
    reused_count = 0
    for trip in trips:
        cached = existing.get(trip.id)
        if cached is not None:
            alignments.append(cached)
            reused_count += 1
            continue
        stops = stops_by_trip.get(trip.id, ())
        result = match_ordered_stops(
            graph,
            stops,
            tuple(value for value in (trip.route_id, trip.headsign, trip.short_name) if value),
            path_cache,
        )
        metrics: dict[str, Any] = {
            **result.metrics,
            "direction_id": trip.direction_id,
            "route_id": trip.route_id,
            "stop_count": len(stops),
        }
        created.append(
            DerivedTripAlignment(
                coordinates=[list(coordinate) for coordinate in result.coordinates],
                derivation_version=DERIVATION_VERSION,
                matcher_config_sha256=config_sha256,
                metrics=metrics,
                reason=result.reason,
                snapshot=snapshot,
                static_feed_version=version,
                status=result.status,
                trip=trip,
            )
        )
    if created:
        DerivedTripAlignment.objects.bulk_create(created, batch_size=500)
        alignments.extend(
            DerivedTripAlignment.objects.filter(
                derivation_version=DERIVATION_VERSION,
                matcher_config_sha256=config_sha256,
                snapshot=snapshot,
                static_feed_version=version,
                trip__in=[alignment.trip for alignment in created],
            ).select_related("trip")
        )
    refresh_geometry_coverage(version)
    return AlignmentDerivationRun(
        alignments=tuple(sorted(alignments, key=lambda alignment: alignment.trip.trip_id)),
        matcher_config_sha256=config_sha256,
        reused_count=reused_count,
    )


def write_review_report(
    report_path: Path,
    version: StaticFeedVersion,
    snapshot: RailInfrastructureSnapshot,
    run: AlignmentDerivationRun,
) -> None:
    """Write accepted, rejected, and ambiguous results without querying a public route."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "derivation_version": DERIVATION_VERSION,
        "infrastructure_snapshot": {
            "attribution": snapshot.attribution,
            "attribution_url": snapshot.attribution_url,
            "content_sha256": snapshot.content_sha256,
            "id": snapshot.id,
            "licence_name": snapshot.licence_name,
            "source_captured_at": snapshot.source_captured_at.isoformat(),
            "source_url": snapshot.source_url,
        },
        "matcher_config_sha256": run.matcher_config_sha256,
        "reused_count": run.reused_count,
        "static_feed_version": str(version.id),
        "trips": [
            {
                "map_url": _map_url(alignment.coordinates),
                "metrics": alignment.metrics,
                "reason": alignment.reason,
                "route_id": alignment.trip.route_id,
                "status": alignment.status,
                "trip_id": alignment.trip.trip_id,
            }
            for alignment in run.alignments
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _eligible_trips(version: StaticFeedVersion) -> list[GtfsTrip]:
    shape_ids = set(
        GtfsShapePoint.objects.filter(feed_version=version).values_list("shape_id", flat=True)
    )
    return [
        trip
        for trip in GtfsTrip.objects.filter(feed_version=version).order_by("route_id", "trip_id")
        if not trip.shape_id or trip.shape_id not in shape_ids
    ]


def _stops_by_trip(trips: list[GtfsTrip]) -> dict[int, tuple[tuple[float, float], ...]]:
    if not trips:
        return {}
    trip_ids = [trip.id for trip in trips]
    stop_times = GtfsStopTime.objects.filter(trip_id__in=trip_ids).order_by(
        "trip_id",
        "stop_sequence",
    )
    stop_ids = {stop_time.stop_id for stop_time in stop_times}
    feed_version_id = trips[0].feed_version_id
    stops = {
        stop_id: (float(longitude), float(latitude))
        for stop_id, latitude, longitude in GtfsStop.objects.filter(
            feed_version_id=feed_version_id,
            stop_id__in=stop_ids,
        ).values_list("stop_id", "latitude", "longitude")
    }
    result: dict[int, list[tuple[float, float]]] = {}
    for stop_time in stop_times:
        coordinate = stops.get(stop_time.stop_id)
        if coordinate is not None:
            result.setdefault(stop_time.trip_id, []).append(coordinate)
    return {trip_id: tuple(coordinates) for trip_id, coordinates in result.items()}


def _matcher_config_sha256() -> str:
    payload = json.dumps(matcher_configuration(), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _map_url(coordinates: list[list[float]]) -> str | None:
    if not coordinates:
        return None
    longitude = sum(coordinate[0] for coordinate in coordinates) / len(coordinates)
    latitude = sum(coordinate[1] for coordinate in coordinates) / len(coordinates)
    return f"https://www.openstreetmap.org/#map=12/{latitude:.6f}/{longitude:.6f}"
