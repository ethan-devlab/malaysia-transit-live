"""Versioned public API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ninja import Schema


class SourceMetadata(Schema):
    """Provenance attached to every public schedule or search result."""

    feed: str
    freshness: Literal["scheduled_only", "unavailable"]
    last_successful_fetch_at: datetime | None
    static_version_id: str


class RouteSearchItem(Schema):
    kind: Literal["route"] = "route"
    route_id: str
    label: str
    name: str
    mode: str
    source: SourceMetadata


class StopSearchItem(Schema):
    kind: Literal["stop"] = "stop"
    stop_id: str
    name: str
    latitude: float
    longitude: float
    source: SourceMetadata


class RouteDetail(Schema):
    route_id: str
    short_name: str
    long_name: str
    description: str
    mode: str
    source: SourceMetadata


class StopDetail(Schema):
    stop_id: str
    name: str
    latitude: float
    longitude: float
    platform_code: str
    source: SourceMetadata


class TripStop(Schema):
    sequence: int
    stop_id: str
    name: str
    latitude: float | None
    longitude: float | None
    arrival_time: str
    departure_time: str


class TripGeometry(Schema):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] | None
    quality: Literal[
        "official_shape",
        "matched_infrastructure",
        "stop_sequence",
        "unavailable",
    ]
    shape_id: str | None
    source: Literal["gtfs", "derived_infrastructure", "scheduled_stops", "none"]
    source_version: str
    attribution: str | None


class TripDetail(Schema):
    trip_id: str
    route_id: str
    headsign: str
    service_date: str
    is_scheduled: bool
    route_color: str
    route_text_color: str
    geometry: TripGeometry
    stops: list[TripStop]
    source: SourceMetadata


class ScheduledJourney(Schema):
    feed: str
    trip_id: str
    route_id: str
    mode: str
    route_label: str
    route_name: str
    origin: str
    destination: str
    service_date: str
    planned_start: str
    planned_end: str
    stop_count: int
    source: SourceMetadata


class NearbyStop(Schema):
    stop_id: str
    name: str
    latitude: float
    longitude: float
    distance_metres: int
    source: SourceMetadata


class VehicleLocation(Schema):
    feed: str
    vehicle_id: str
    trip_id: str
    route_id: str
    latitude: float
    longitude: float
    bearing: float | None
    speed_metres_per_second: float | None
    position_reported_at: datetime | None
    fetched_at: datetime
    freshness: Literal["live", "stale"]
    static_version_id: str | None


class SearchResponse(Schema):
    query: str
    journeys: list[ScheduledJourney]
    routes: list[RouteSearchItem]
    stops: list[StopSearchItem]
    vehicles: list[VehicleLocation]


class DataStatus(Schema):
    feed: str
    static_state: Literal["active", "unavailable"]
    realtime_state: Literal["available", "awaiting_first_fetch", "scheduled_only", "unavailable"]
    active_version_id: str | None
    last_successful_static_fetch_at: datetime | None
    last_successful_realtime_fetch_at: datetime | None


DashboardMode = Literal["bus", "mrt", "lrt", "monorail", "rail", "unknown"]
DashboardRealtimeState = Literal[
    "available",
    "awaiting_first_fetch",
    "scheduled_only",
    "unavailable",
]


class DashboardOption(Schema):
    key: str
    label: str
    count: int


class DashboardFilters(Schema):
    mode: str
    operator: str | None
    region: str | None


class DashboardVehicle(Schema):
    feed: str
    feed_display_name: str
    operator_key: str
    operator_name: str
    region_key: str
    region_name: str
    agency_names: list[str]
    mode: DashboardMode
    vehicle_id: str
    trip_id: str
    route_id: str
    route_name: str
    trip_headsign: str
    latitude: float
    longitude: float
    bearing: float | None
    speed_metres_per_second: float | None
    position_reported_at: datetime | None
    fetched_at: datetime
    freshness: Literal["live", "stale"]
    static_version_id: str | None
    next_scheduled_stop: str | None


class DashboardGeometryCoverage(Schema):
    trip_count: int
    official_shape_count: int
    matched_infrastructure_count: int
    stop_sequence_count: int
    unavailable_count: int


class DashboardSource(Schema):
    feed: str
    display_name: str
    operator_key: str
    operator_name: str
    region_key: str
    region_name: str
    agency_names: list[str]
    modes: list[DashboardMode]
    static_state: Literal["active", "unavailable"]
    realtime_state: DashboardRealtimeState
    last_successful_static_fetch_at: datetime | None
    last_successful_realtime_fetch_at: datetime | None
    vehicle_count: int
    live_vehicle_count: int
    stale_vehicle_count: int
    unknown_vehicle_count: int
    geometry_coverage: DashboardGeometryCoverage


class DashboardSummary(Schema):
    feed_count: int
    vehicle_count: int
    live_vehicle_count: int
    stale_vehicle_count: int
    unknown_vehicle_count: int
    scheduled_only_feed_count: int
    unavailable_feed_count: int
    awaiting_first_fetch_feed_count: int


class DashboardVehiclePage(Schema):
    items: list[DashboardVehicle]
    total_count: int
    returned_count: int
    next_cursor: str | None
    truncated: bool


class DashboardResponse(Schema):
    generated_at: datetime
    filters: DashboardFilters
    options: dict[str, list[DashboardOption]]
    summary: DashboardSummary
    sources: list[DashboardSource]
    vehicles: DashboardVehiclePage
