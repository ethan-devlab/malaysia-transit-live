"""Read-only Server-Sent Event snapshots for validated vehicle locations."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, HttpResponseNotAllowed, StreamingHttpResponse
from django.utils import timezone

from transit.models import VehicleSnapshot

LIVE_FRESHNESS_SECONDS = 90
VEHICLE_RETENTION_SECONDS = 15 * 60


def vehicle_snapshot_stream(request: HttpRequest) -> StreamingHttpResponse | HttpResponseNotAllowed:
    """Emit one current snapshot and let EventSource reconnect without proxy buffering."""
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    response = StreamingHttpResponse(
        _snapshot_events(),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-store, no-transform"
    response["Connection"] = "keep-alive"
    response["X-Accel-Buffering"] = "no"
    return response


def _snapshot_events() -> Iterator[str]:
    now = timezone.now()
    cutoff = now - timedelta(seconds=VEHICLE_RETENTION_SECONDS)
    live_cutoff = now - timedelta(seconds=LIVE_FRESHNESS_SECONDS)
    snapshots = VehicleSnapshot.objects.filter(
        validation_state=VehicleSnapshot.ValidationState.VALIDATED,
        fetched_at__gte=cutoff,
    ).select_related("feed")
    payload = {
        "generated_at": now,
        "vehicles": [
            {
                "feed": snapshot.feed.slug,
                "vehicle_id": snapshot.vehicle_id,
                "trip_id": snapshot.trip_id,
                "route_id": snapshot.route_id,
                "latitude": float(snapshot.latitude),
                "longitude": float(snapshot.longitude),
                "fetched_at": snapshot.fetched_at,
                "freshness": "live" if snapshot.fetched_at >= live_cutoff else "stale",
            }
            for snapshot in snapshots
        ],
    }
    serialised = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":"))
    yield "retry: 5000\n"
    yield f"event: vehicle-snapshot\ndata: {serialised}\n\n"
