"""Import one downloaded static GTFS ZIP into an atomically activated version."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from transit.models import TransitFeed
from transit.services.static_import import import_static_gtfs_archive
from transit.services.static_import.contracts import StaticImportError


class Command(BaseCommand):
    """Load a previously archived GTFS ZIP without directly exposing an upstream fetch."""

    help = "Stage, validate, and activate a GTFS static ZIP for one feed."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--feed", required=True, help="Stable feed slug from the feed registry."
        )
        parser.add_argument("--archive", required=True, help="Path to the downloaded GTFS ZIP.")
        parser.add_argument(
            "--archive-object-key",
            default="",
            help="R2 object key already assigned to the preserved original ZIP.",
        )

    def handle(self, *args: Any, **options: Any) -> str:
        feed_slug = options["feed"]
        archive_path = Path(options["archive"])
        archive_object_key = options["archive_object_key"]
        try:
            feed = TransitFeed.objects.get(slug=feed_slug)
        except TransitFeed.DoesNotExist as error:
            raise CommandError(f"Unknown feed: {feed_slug}") from error

        try:
            result = import_static_gtfs_archive(feed, archive_path, archive_object_key)
        except StaticImportError as error:
            location = f" row {error.row_number}" if error.row_number else ""
            raise CommandError(
                f"{error.code} in {error.source_file}{location}: {error.detail}"
            ) from error

        return self.style.SUCCESS(
            f"Activated version {result.version_id} with {result.record_counts['trips']} trips "
            f"and {result.record_counts['stop_times']} stop times."
        )
