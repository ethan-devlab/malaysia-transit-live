"""Composition root for the versioned public transit API."""

from ninja import NinjaAPI

from transit.http.journeys_api import router as journeys_router
from transit.http.network_api import router as network_router
from transit.http.status_api import router as status_router

api = NinjaAPI(
    title="Malaysia Transit Live API",
    version="1.0.0",
    urls_namespace="malaysia-transit-v1",
    docs_url=None,
)
api.add_router("", network_router)
api.add_router("", journeys_router)
api.add_router("", status_router)
