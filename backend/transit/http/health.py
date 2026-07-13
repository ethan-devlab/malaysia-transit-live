"""Health-check endpoint for deployment platforms and the edge gateway."""

from django.http import HttpRequest, JsonResponse


def health(_request: HttpRequest) -> JsonResponse:
    """Return a dependency-free liveness response."""
    return JsonResponse({"status": "ok"})
