"""Root URL routing."""

from django.contrib import admin
from django.urls import path

from transit.http.api import api
from transit.http.health import health
from transit.http.stream import dashboard_snapshot_stream, vehicle_snapshot_stream

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/healthz", health, name="healthz"),
    path("api/v1/", api.urls),
    path("stream/v1/vehicles", vehicle_snapshot_stream, name="vehicle-snapshot-stream"),
    path("stream/v1/dashboard", dashboard_snapshot_stream, name="dashboard-snapshot-stream"),
]
