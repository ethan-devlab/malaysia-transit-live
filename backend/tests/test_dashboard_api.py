import pytest
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from transit.http.dashboard_api import dashboard
from transit.http.stream import dashboard_snapshot_stream
from transit.models import GtfsAgency, GtfsRoute, StaticFeedVersion, TransitFeed, VehicleSnapshot
from transit.services.feed_registry import OFFICIAL_FEEDS


def _feed(
    slug: str,
    *,
    operator_key: str = "rapid-kl",
    operator_name: str = "Rapid KL",
    region_key: str = "kuala-lumpur",
    region_name: str = "Kuala Lumpur",
    realtime: bool = True,
) -> tuple[TransitFeed, StaticFeedVersion]:
    feed = TransitFeed.objects.create(
        display_name=slug,
        is_realtime_enabled=realtime,
        operator_key=operator_key,
        operator_name=operator_name,
        realtime_source_url="https://api.data.gov.my/gtfs-realtime/vehicle-position/test"
        if realtime
        else "",
        region_key=region_key,
        region_name=region_name,
        slug=slug,
        static_source_url="https://api.data.gov.my/gtfs-static/test",
    )
    version = StaticFeedVersion.objects.create(
        content_sha256="a" * 64,
        feed=feed,
        source_url=feed.static_source_url,
        status=StaticFeedVersion.Status.ACTIVE,
    )
    return feed, version


def _vehicle(
    feed: TransitFeed,
    version: StaticFeedVersion,
    vehicle_id: str,
    *,
    route_id: str = "BUS-1",
) -> VehicleSnapshot:
    return VehicleSnapshot.objects.create(
        feed=feed,
        feed_version=version,
        fetched_at=timezone.now(),
        latitude="3.139000",
        longitude="101.686900",
        route_id=route_id,
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
        vehicle_id=vehicle_id,
    )


def test_official_feed_registry_has_canonical_dashboard_metadata() -> None:
    metadata = {definition.slug: definition for definition in OFFICIAL_FEEDS}

    assert metadata["ktmb"].operator_key == "ktmb"
    assert metadata["rapid-rail-kl"].operator_key == "rapid-kl"
    assert metadata["rapid-rail-kl"].region_key == "kuala-lumpur"
    assert metadata["mybas-kuching"].operator_key == "bas-my"
    assert metadata["mybas-kuching"].region_name == "Kuching"


@pytest.mark.django_db
def test_dashboard_returns_feed_catalogue_and_enriched_vehicle() -> None:
    feed, version = _feed("rapid-bus-kl")
    agency = GtfsAgency.objects.create(
        agency_id="rapid",
        feed_version=version,
        name="Rapid Rail Sdn Bhd",
        timezone="Asia/Kuala_Lumpur",
    )
    GtfsRoute.objects.create(
        agency_id=agency.agency_id,
        feed_version=version,
        long_name="City Bus",
        route_id="BUS-1",
        route_type=3,
    )
    _vehicle(feed, version, "bus-1")

    result = dashboard(RequestFactory().get("/api/v1/dashboard"))

    assert result.summary.vehicle_count == 1
    assert result.sources[0].operator_name == "Rapid KL"
    assert result.sources[0].region_name == "Kuala Lumpur"
    assert result.vehicles.items[0].mode == "bus"
    assert result.vehicles.items[0].agency_names == ["Rapid Rail Sdn Bhd"]


@pytest.mark.django_db
def test_dashboard_uses_materialised_geometry_coverage_without_trip_scans() -> None:
    _, version = _feed("rapid-rail-kl")
    version.record_counts = {
        "trips": 120,
        "trips_with_shape": 119,
        "trips_without_shape": 1,
        "orphan_trip_shapes": 1,
    }
    version.save(update_fields=("record_counts",))

    with CaptureQueriesContext(connection) as queries:
        result = dashboard(RequestFactory().get("/api/v1/dashboard"))

    assert result.sources[0].geometry_coverage.dict() == {
        "trip_count": 120,
        "official_shape_count": 118,
        "matched_infrastructure_count": 0,
        "matched_infrastructure_derived_at": None,
        "stop_sequence_count": 2,
        "unavailable_count": 0,
    }
    assert not any('FROM "transit_gtfstrip"' in query["sql"] for query in queries.captured_queries)


@pytest.mark.django_db
def test_dashboard_filters_by_mode_operator_and_region() -> None:
    bus_feed, bus_version = _feed("rapid-bus-kl")
    rail_feed, rail_version = _feed(
        "ktmb",
        operator_key="ktmb",
        operator_name="KTMB",
        region_key="national",
        region_name="Malaysia",
    )
    GtfsRoute.objects.create(
        feed_version=bus_version,
        long_name="City Bus",
        route_id="BUS-1",
        route_type=3,
    )
    GtfsRoute.objects.create(
        feed_version=rail_version,
        long_name="Main Rail",
        route_id="RAIL-1",
        route_type=2,
    )
    _vehicle(bus_feed, bus_version, "bus-1")
    _vehicle(rail_feed, rail_version, "rail-1", route_id="RAIL-1")

    result = dashboard(
        RequestFactory().get("/api/v1/dashboard"),
        mode="bus",
        operator="rapid-kl",
        region="kuala-lumpur",
    )

    assert [vehicle.vehicle_id for vehicle in result.vehicles.items] == ["bus-1"]
    assert [source.feed for source in result.sources] == ["rapid-bus-kl"]


@pytest.mark.django_db
def test_dashboard_keeps_unknown_route_vehicle_and_supports_cursor_pages() -> None:
    feed, version = _feed("unknown-route")
    GtfsRoute.objects.create(
        feed_version=version,
        long_name="City Bus",
        route_id="BUS-1",
        route_type=3,
    )
    for index in range(3):
        _vehicle(feed, version, f"bus-{index}", route_id="missing" if index == 0 else "BUS-1")

    first_page = dashboard(RequestFactory().get("/api/v1/dashboard"), limit=2)
    second_page = dashboard(
        RequestFactory().get("/api/v1/dashboard"),
        cursor=first_page.vehicles.next_cursor,
        limit=2,
    )

    assert first_page.vehicles.total_count == 3
    assert first_page.vehicles.truncated is True
    assert first_page.vehicles.items[0].mode == "unknown"
    assert {vehicle.vehicle_id for vehicle in second_page.vehicles.items} == {"bus-2"}


@pytest.mark.django_db
def test_dashboard_marks_scheduled_only_and_unavailable_feeds() -> None:
    scheduled_feed, scheduled_version = _feed("scheduled", realtime=False)
    TransitFeed.objects.create(
        display_name="Unavailable",
        is_realtime_enabled=True,
        operator_key="unknown",
        operator_name="Unknown",
        region_key="unknown",
        region_name="Unclassified",
        realtime_source_url="https://api.data.gov.my/gtfs-realtime/vehicle-position/unavailable",
        slug="unavailable",
        static_source_url="https://api.data.gov.my/gtfs-static/unavailable",
    )
    GtfsRoute.objects.create(
        feed_version=scheduled_version,
        long_name="Scheduled Rail",
        route_id="RAIL-1",
        route_type=2,
    )
    _vehicle(scheduled_feed, scheduled_version, "scheduled-1", route_id="RAIL-1")

    result = dashboard(RequestFactory().get("/api/v1/dashboard"))
    statuses = {source.feed: source.realtime_state for source in result.sources}

    assert statuses["scheduled"] == "scheduled_only"
    assert statuses["unavailable"] == "unavailable"


@pytest.mark.django_db
def test_dashboard_stream_uses_dashboard_serializer_and_filters() -> None:
    feed, version = _feed("rapid-bus-kl")
    GtfsRoute.objects.create(feed_version=version, route_id="BUS-1", route_type=3)
    _vehicle(feed, version, "bus-1")

    response = dashboard_snapshot_stream(RequestFactory().get("/stream/v1/dashboard?mode=bus"))
    payload = b"".join(response.streaming_content).decode()

    assert "event: dashboard-snapshot" in payload
    assert '"mode":"bus"' in payload
    assert '"vehicle_id":"bus-1"' in payload


@pytest.mark.django_db
def test_dashboard_metadata_queries_are_batched_for_multiple_vehicles() -> None:
    feed, version = _feed("rapid-bus-kl")
    GtfsRoute.objects.create(feed_version=version, route_id="BUS-1", route_type=3)
    for index in range(5):
        _vehicle(feed, version, f"bus-{index}")

    with CaptureQueriesContext(connection) as queries:
        dashboard(RequestFactory().get("/api/v1/dashboard"))

    assert len(queries) < 12
