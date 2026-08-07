"""Feed registry and atomic static-dataset version lifecycle models."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q


class TransitFeed(models.Model):
    """A government-published GTFS dataset, identified by a stable feed slug."""

    slug = models.SlugField(max_length=80, unique=True)
    display_name = models.CharField(max_length=160)
    static_source_url = models.URLField()
    realtime_source_url = models.URLField(blank=True)
    operator_key = models.SlugField(max_length=80, default="")
    operator_name = models.CharField(max_length=160, default="")
    region_key = models.SlugField(max_length=80, default="")
    region_name = models.CharField(max_length=160, default="")
    agency_timezone = models.CharField(max_length=64, default="Asia/Kuala_Lumpur")
    realtime_priority = models.PositiveSmallIntegerField(default=0)
    is_realtime_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[tuple[str, ...]] = ("slug",)

    def __str__(self) -> str:
        return self.slug


class StaticFeedVersion(models.Model):
    """A staged, rejected, archived, or atomically active static GTFS snapshot."""

    class Status(models.TextChoices):
        STAGED = "staged", "Staged"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    feed = models.ForeignKey(TransitFeed, on_delete=models.PROTECT, related_name="versions")
    status = models.CharField(max_length=16, choices=Status, default=Status.STAGED)
    source_url = models.URLField()
    content_sha256 = models.CharField(max_length=64, db_index=True)
    archive_object_key = models.CharField(max_length=512, blank=True)
    manifest = models.JSONField(default=dict)
    record_counts = models.JSONField(default=dict)
    warnings_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=("feed",),
                condition=Q(status="active"),
                name="one_active_static_version_per_feed",
            )
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed", "status")),
            models.Index(fields=("feed", "started_at")),
        ]

    def __str__(self) -> str:
        return f"{self.feed.slug}:{self.id} ({self.status})"


class StaticImportIssue(models.Model):
    """A validation warning or error retained with the version for operations review."""

    class Severity(models.TextChoices):
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    version = models.ForeignKey(
        StaticFeedVersion,
        on_delete=models.CASCADE,
        related_name="import_issues",
    )
    severity = models.CharField(max_length=8, choices=Severity)
    code = models.CharField(max_length=80)
    source_file = models.CharField(max_length=100)
    row_number = models.PositiveIntegerField(null=True, blank=True)
    detail = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("version", "severity")),
            models.Index(fields=("version", "source_file")),
        ]


class UpstreamFetchAttempt(models.Model):
    """Redacted operational record for one static or realtime upstream request."""

    class Kind(models.TextChoices):
        STATIC = "static", "Static GTFS"
        REALTIME = "realtime", "GTFS Realtime"

    feed = models.ForeignKey(TransitFeed, on_delete=models.CASCADE, related_name="fetch_attempts")
    kind = models.CharField(max_length=16, choices=Kind)
    succeeded = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    detail = models.CharField(max_length=240, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=("feed", "kind", "completed_at")),
            models.Index(fields=("kind", "succeeded", "completed_at")),
        ]
