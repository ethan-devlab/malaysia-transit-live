"""Bounded, validated latest vehicle positions from GTFS Realtime feeds."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from transit.models.feed import StaticFeedVersion, TransitFeed


class VehicleSnapshot(models.Model):
    """The latest usable or rejected location for one feed-scoped vehicle identifier."""

    class ValidationState(models.TextChoices):
        VALIDATED = "validated", "Validated"
        ORPHAN_REFERENCE = "orphan_reference", "Orphan reference"
        OUT_OF_COVERAGE = "out_of_coverage", "Out of coverage"

    feed = models.ForeignKey(
        TransitFeed, on_delete=models.CASCADE, related_name="vehicle_snapshots"
    )
    feed_version = models.ForeignKey(
        StaticFeedVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vehicle_snapshots",
    )
    vehicle_id = models.CharField(max_length=160)
    trip_id = models.CharField(max_length=160, blank=True)
    route_id = models.CharField(max_length=160, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    bearing = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    speed_metres_per_second = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )
    position_reported_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField()
    validation_state = models.CharField(max_length=24, choices=ValidationState)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed", "vehicle_id"),
                name="latest_snapshot_per_feed_vehicle",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed", "validation_state", "fetched_at")),
            models.Index(fields=("feed_version", "trip_id")),
        ]
