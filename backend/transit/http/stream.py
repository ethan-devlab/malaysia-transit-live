"""Read-only Server-Sent Event snapshots for validated vehicle locations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from ninja.errors import HttpError

from transit.http.dashboard_api import dashboard
from transit.http.status_api import (
    VEHICLE_SNAPSHOT_LIMIT,
    _recent_validated_vehicle_snapshots,
    vehicle_location,
)


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


def dashboard_snapshot_stream(request: HttpRequest) -> StreamingHttpResponse | HttpResponseNotAllowed:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    try:
        mode = request.GET.get("mode", "all")
        operator = request.GET.get("operator") or None
        region = request.GET.get("region") or None
        cursor = request.GET.get("cursor") or None
        limit = int(request.GET.get("limit", "100"))
        query_values = (mode, operator or "", region or "", cursor or "", str(limit))
        cache_key = "dashboard-sse:" + hashlib.sha256("|".join(query_values).encode()).hexdigest()
        payload = cache.get(cache_key)
        if payload is None:
            result = dashboard(
                request,
                mode=mode,
                operator=operator,
                region=region,
                cursor=cursor,
                limit=limit,
            )
            payload = result.model_dump(mode="json")
            cache.set(cache_key, payload, timeout=5)
    except (HttpError, ValueError) as error:
        status_code = error.status_code if isinstance(error, HttpError) else 422
        return JsonResponse({"detail": "Invalid dashboard stream query."}, status=status_code)
    response = StreamingHttpResponse(
        _dashboard_snapshot_events(payload),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-store, no-transform"
    response["Connection"] = "keep-alive"
    response["X-Accel-Buffering"] = "no"
    return response


def _snapshot_events() -> Iterator[str]:
    now = timezone.now()
    snapshots = _recent_validated_vehicle_snapshots(now, limit=VEHICLE_SNAPSHOT_LIMIT)
    payload = {
        "generated_at": now,
        "vehicles": [
            vehicle_location(snapshot, now).model_dump(mode="json") for snapshot in snapshots
        ],
    }
    serialised = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":"))
    yield "retry: 5000\n"
    yield f"event: vehicle-snapshot\ndata: {serialised}\n\n"


def _dashboard_snapshot_events(payload: dict[str, object]) -> Iterator[str]:
    serialised = json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":"))
    yield "retry: 5000\n"
    yield f"event: dashboard-snapshot\ndata: {serialised}\n\n"
