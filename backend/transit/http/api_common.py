"""Shared v1 API lookup and mapping helpers."""

from __future__ import annotations

from ninja.errors import HttpError

from transit.http.query_helpers import active_versions, source_metadata
from transit.http.schemas import RouteSearchItem, StopSearchItem
from transit.models import GtfsRoute, GtfsStop, StaticFeedVersion, TransitFeed

ROUTE_MODE_NAMES: dict[int, str] = {
    0: "tram",
    1: "metro",
    2: "rail",
    3: "bus",
    4: "ferry",
    5: "cable_tram",
    6: "aerial_lift",
    7: "funicular",
    11: "trolleybus",
    12: "monorail",
}


def active_feed_version(feed_slug: str) -> tuple[TransitFeed, StaticFeedVersion]:
    """Find a named feed and its sole current static version."""
    try:
        feed = TransitFeed.objects.get(slug=feed_slug)
    except TransitFeed.DoesNotExist as error:
        raise HttpError(404, "Feed is not registered.") from error
    version = active_versions().filter(feed=feed).first()
    if version is None:
        raise HttpError(404, "Feed has no active static version.")
    return feed, version


def route_mode(route_type: int) -> str:
    """Map standardized GTFS route types to public transport mode labels."""
    return ROUTE_MODE_NAMES.get(route_type, "other")


def route_search_item(route: GtfsRoute) -> RouteSearchItem:
    """Convert a query row into the public typed search contract."""
    return RouteSearchItem(
        route_id=route.route_id,
        label=route.short_name or route.long_name or route.route_id,
        name=route.long_name,
        mode=route_mode(route.route_type),
        source=source_metadata(route.feed_version.feed, route.feed_version),
    )


def stop_search_item(stop: GtfsStop) -> StopSearchItem:
    """Convert a stop query row into the public typed search contract."""
    return StopSearchItem(
        stop_id=stop.stop_id,
        name=stop.name,
        latitude=float(stop.latitude),
        longitude=float(stop.longitude),
        source=source_metadata(stop.feed_version.feed, stop.feed_version),
    )
