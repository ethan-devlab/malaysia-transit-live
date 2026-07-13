"""Normalized GTFS static records, always scoped to one immutable feed version."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from transit.models.feed import StaticFeedVersion


class GtfsAgency(models.Model):
    feed_version = models.ForeignKey(StaticFeedVersion, on_delete=models.CASCADE)
    agency_id = models.CharField(max_length=160)
    name = models.CharField(max_length=255)
    url = models.URLField(blank=True)
    timezone = models.CharField(max_length=64)
    language = models.CharField(max_length=16, blank=True)
    phone = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed_version", "agency_id"),
                name="unique_agency_per_static_version",
            )
        ]


class GtfsRoute(models.Model):
    feed_version = models.ForeignKey(StaticFeedVersion, on_delete=models.CASCADE)
    route_id = models.CharField(max_length=160)
    agency_id = models.CharField(max_length=160, blank=True)
    short_name = models.CharField(max_length=160, blank=True)
    long_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    route_type = models.PositiveSmallIntegerField()
    route_color = models.CharField(max_length=6, blank=True)
    text_color = models.CharField(max_length=6, blank=True)
    sort_order = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed_version", "route_id"),
                name="unique_route_per_static_version",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed_version", "short_name")),
            models.Index(fields=("feed_version", "long_name")),
        ]


class GtfsStop(models.Model):
    feed_version = models.ForeignKey(StaticFeedVersion, on_delete=models.CASCADE)
    stop_id = models.CharField(max_length=160)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_type = models.PositiveSmallIntegerField(default=0)
    parent_station_id = models.CharField(max_length=160, blank=True)
    platform_code = models.CharField(max_length=80, blank=True)
    wheelchair_boarding = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed_version", "stop_id"),
                name="unique_stop_per_static_version",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed_version", "latitude", "longitude")),
            models.Index(fields=("feed_version", "name")),
        ]


class GtfsService(models.Model):
    feed_version = models.ForeignKey(StaticFeedVersion, on_delete=models.CASCADE)
    service_id = models.CharField(max_length=160)
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed_version", "service_id"),
                name="unique_service_per_static_version",
            )
        ]


class GtfsServiceException(models.Model):
    service = models.ForeignKey(GtfsService, on_delete=models.CASCADE, related_name="exceptions")
    service_date = models.DateField()
    exception_type = models.PositiveSmallIntegerField()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("service", "service_date"),
                name="unique_service_exception_date",
            )
        ]


class GtfsTrip(models.Model):
    feed_version = models.ForeignKey(StaticFeedVersion, on_delete=models.CASCADE)
    trip_id = models.CharField(max_length=160)
    route_id = models.CharField(max_length=160)
    service_id = models.CharField(max_length=160)
    headsign = models.CharField(max_length=255, blank=True)
    short_name = models.CharField(max_length=160, blank=True)
    direction_id = models.PositiveSmallIntegerField(null=True, blank=True)
    block_id = models.CharField(max_length=160, blank=True)
    shape_id = models.CharField(max_length=160, blank=True)
    wheelchair_accessible = models.PositiveSmallIntegerField(default=0)
    bikes_allowed = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed_version", "trip_id"),
                name="unique_trip_per_static_version",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed_version", "route_id")),
            models.Index(fields=("feed_version", "service_id")),
        ]


class GtfsStopTime(models.Model):
    trip = models.ForeignKey(GtfsTrip, on_delete=models.CASCADE, related_name="stop_times")
    stop_id = models.CharField(max_length=160)
    stop_sequence = models.PositiveIntegerField()
    arrival_time = models.CharField(max_length=8, blank=True)
    departure_time = models.CharField(max_length=8, blank=True)
    arrival_seconds = models.PositiveIntegerField(null=True, blank=True)
    departure_seconds = models.PositiveIntegerField(null=True, blank=True)
    stop_headsign = models.CharField(max_length=255, blank=True)
    pickup_type = models.PositiveSmallIntegerField(default=0)
    drop_off_type = models.PositiveSmallIntegerField(default=0)
    timepoint = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("trip", "stop_sequence"),
                name="unique_stop_sequence_per_trip",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("trip", "stop_sequence")),
            models.Index(fields=("stop_id",)),
        ]
