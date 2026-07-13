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


class SearchResponse(Schema):
    query: str
    routes: list[RouteSearchItem]
    stops: list[StopSearchItem]


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
    arrival_time: str
    departure_time: str


class TripDetail(Schema):
    trip_id: str
    route_id: str
    headsign: str
    service_date: str
    is_scheduled: bool
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


class DataStatus(Schema):
    feed: str
    static_state: Literal["active", "unavailable"]
    active_version_id: str | None
    last_successful_static_fetch_at: datetime | None
    last_successful_realtime_fetch_at: datetime | None
