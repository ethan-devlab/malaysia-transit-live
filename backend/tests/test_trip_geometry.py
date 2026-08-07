from datetime import date

import pytest
from django.db import connection
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext

from transit.http.network_api import trip_detail
from transit.models import (
    GtfsRoute,
    GtfsService,
    GtfsShapePoint,
    GtfsStop,
    GtfsStopTime,
    GtfsTrip,
    StaticFeedVersion,
    TransitFeed,
)
from transit.services.trip_geometry import ResolvedTripGeometry, resolve_trip_geometry


def _scheduled_trip(
    slug: str,
    *,
    shape_id: str = "shape-a",
    with_stops: bool = True,
) -> tuple[TransitFeed, StaticFeedVersion, GtfsTrip]:
    feed = TransitFeed.objects.create(
        display_name=slug,
        slug=slug,
        static_source_url=f"https://example.com/{slug}.zip",
    )
    version = StaticFeedVersion.objects.create(
        content_sha256=(slug[0] * 64),
        feed=feed,
        source_url=feed.static_source_url,
        status=StaticFeedVersion.Status.ACTIVE,
    )
    GtfsRoute.objects.create(
        feed_version=version,
        route_color="dc241f",
        route_id="R1",
        route_type=1,
        text_color="ffffff",
    )
    service = GtfsService.objects.create(
        end_date=date(2026, 12, 31),
        feed_version=version,
        friday=True,
        monday=True,
        saturday=True,
        service_id="daily",
        start_date=date(2026, 1, 1),
        sunday=True,
        thursday=True,
        tuesday=True,
        wednesday=True,
    )
    trip = GtfsTrip.objects.create(
        feed_version=version,
        headsign="Central",
        route_id="R1",
        service_id=service.service_id,
        shape_id=shape_id,
        trip_id="T1",
    )
    if with_stops:
        for sequence, (stop_id, latitude, longitude) in enumerate(
            (("S1", "3.100000", "101.600000"), ("S2", "3.200000", "101.700000"))
        ):
            GtfsStop.objects.create(
                feed_version=version,
                latitude=latitude,
                longitude=longitude,
                name=stop_id,
                stop_id=stop_id,
            )
            GtfsStopTime.objects.create(
                arrival_time=f"08:{sequence}0:00",
                departure_time=f"08:{sequence}0:00",
                stop_id=stop_id,
                stop_sequence=sequence,
                trip=trip,
            )
    return feed, version, trip


@pytest.mark.django_db
@override_settings(LOCAL_ONLY=True)
def test_trip_detail_returns_official_gtfs_geometry_and_normalised_colours() -> None:
    feed, version, trip = _scheduled_trip("rapid-rail-geometry")
    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude="3.100000",
                longitude="101.600000",
                sequence=0,
                shape_id=trip.shape_id,
            ),
            GtfsShapePoint(
                feed_version=version,
                latitude="3.160000",
                longitude="101.620000",
                sequence=1,
                shape_id=trip.shape_id,
            ),
            GtfsShapePoint(
                feed_version=version,
                latitude="3.200000",
                longitude="101.700000",
                sequence=2,
                shape_id=trip.shape_id,
            ),
        ]
    )

    response = Client().get(
        f"/api/v1/trips/{feed.slug}/{trip.trip_id}",
        {"service_date": "2026-08-07"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route_color"] == "DC241F"
    assert payload["route_text_color"] == "FFFFFF"
    assert payload["geometry"] == {
        "type": "LineString",
        "coordinates": [[101.6, 3.1], [101.62, 3.16], [101.7, 3.2]],
        "quality": "official_shape",
        "shape_id": "shape-a",
        "source": "gtfs",
        "source_version": str(version.id),
        "attribution": None,
    }
    assert "eta" not in response.content.decode().lower()


@pytest.mark.django_db
def test_resolver_orders_official_then_matched_then_stop_sequence_then_unavailable() -> None:
    _, version, trip = _scheduled_trip("resolver-order")
    stops = ((101.6, 3.1), (101.7, 3.2))
    matched = ResolvedTripGeometry(
        attribution="OpenStreetMap contributors",
        coordinates=((101.6, 3.1), (101.65, 3.14), (101.7, 3.2)),
        quality="matched_infrastructure",
        shape_id=None,
        source="derived_infrastructure",
        source_version=str(version.id),
    )

    assert resolve_trip_geometry(version, trip, stops, matched).quality == "matched_infrastructure"
    assert resolve_trip_geometry(version, trip, stops).quality == "stop_sequence"
    assert resolve_trip_geometry(version, trip, ()).quality == "unavailable"

    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude="3.100000",
                longitude="101.600000",
                sequence=0,
                shape_id=trip.shape_id,
            ),
            GtfsShapePoint(
                feed_version=version,
                latitude="3.200000",
                longitude="101.700000",
                sequence=1,
                shape_id=trip.shape_id,
            ),
        ]
    )
    assert resolve_trip_geometry(version, trip, stops, matched).quality == "official_shape"


@pytest.mark.django_db
@override_settings(LOCAL_ONLY=True)
def test_shape_endpoint_mismatch_downgrades_and_missing_stops_remain_available() -> None:
    feed, version, trip = _scheduled_trip("misaligned-shape")
    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude="6.100000",
                longitude="116.100000",
                sequence=0,
                shape_id=trip.shape_id,
            ),
            GtfsShapePoint(
                feed_version=version,
                latitude="6.200000",
                longitude="116.200000",
                sequence=1,
                shape_id=trip.shape_id,
            ),
        ]
    )

    fallback_response = Client().get(
        f"/api/v1/trips/{feed.slug}/{trip.trip_id}",
        {"service_date": "2026-08-07"},
    )
    empty_feed, _, empty_trip = _scheduled_trip("empty-geometry", with_stops=False)
    unavailable_response = Client().get(
        f"/api/v1/trips/{empty_feed.slug}/{empty_trip.trip_id}",
        {"service_date": "2026-08-07"},
    )

    assert fallback_response.status_code == 200
    assert fallback_response.json()["geometry"]["quality"] == "stop_sequence"
    assert unavailable_response.status_code == 200
    assert unavailable_response.json()["geometry"]["quality"] == "unavailable"
    assert unavailable_response.json()["geometry"]["coordinates"] is None
    assert unavailable_response.json()["stops"] == []


@pytest.mark.django_db
def test_official_shape_may_extend_beyond_terminal_stops() -> None:
    _, version, trip = _scheduled_trip("extended-shape")
    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude=latitude,
                longitude=longitude,
                sequence=sequence,
                shape_id=trip.shape_id,
            )
            for sequence, (longitude, latitude) in enumerate(
                (
                    ("101.580000", "3.080000"),
                    ("101.600000", "3.100000"),
                    ("101.700000", "3.200000"),
                    ("101.720000", "3.220000"),
                )
            )
        ]
    )

    geometry = resolve_trip_geometry(version, trip, ((101.6, 3.1), (101.7, 3.2)))

    assert geometry.quality == "official_shape"
    assert geometry.coordinates is not None
    assert len(geometry.coordinates) == 4


@pytest.mark.django_db
def test_trip_detail_query_count_is_constant_with_shape_point_count() -> None:
    feed, version, trip = _scheduled_trip("query-count")
    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude="3.100000",
                longitude="101.600000",
                sequence=0,
                shape_id=trip.shape_id,
            ),
            GtfsShapePoint(
                feed_version=version,
                latitude="3.200000",
                longitude="101.700000",
                sequence=101,
                shape_id=trip.shape_id,
            ),
        ]
    )
    request = RequestFactory().get("/api/v1/trips")

    with CaptureQueriesContext(connection) as small_queries:
        trip_detail(request, feed.slug, trip.trip_id, date(2026, 8, 7))

    GtfsShapePoint.objects.bulk_create(
        [
            GtfsShapePoint(
                feed_version=version,
                latitude=f"{3.1 + sequence / 1000:.6f}",
                longitude=f"{101.6 + sequence / 1000:.6f}",
                sequence=sequence,
                shape_id=trip.shape_id,
            )
            for sequence in range(1, 101)
        ]
    )
    with CaptureQueriesContext(connection) as large_queries:
        trip_detail(request, feed.slug, trip.trip_id, date(2026, 8, 7))

    assert len(small_queries) == len(large_queries)
