"""Require Cloudflare Worker provenance for public backend API requests."""

from __future__ import annotations

import hmac

from django.conf import settings
from django.http import HttpRequest, JsonResponse

WORKER_SECRET_HEADER = "X-Transit-Edge-Secret"
PUBLIC_HEALTH_PATH = "/api/v1/healthz"


class WorkerOriginVerificationMiddleware:
    """Reject direct public API access unless the loopback-only profile is active."""

    def __init__(self, get_response: object) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> object:
        if (
            settings.LOCAL_ONLY
            or request.path == PUBLIC_HEALTH_PATH
            or not _is_public_api(request.path)
        ):
            return self._get_response(request)

        expected_secret = settings.WORKER_ORIGIN_SECRET
        if not expected_secret:
            return JsonResponse({"detail": "Edge origin verification is unavailable."}, status=503)
        supplied_secret = request.headers.get(WORKER_SECRET_HEADER, "")
        if not hmac.compare_digest(supplied_secret, expected_secret):
            return JsonResponse({"detail": "Edge origin verification failed."}, status=403)
        return self._get_response(request)


def _is_public_api(path: str) -> bool:
    return path.startswith(("/admin/", "/api/", "/stream/"))
