"""Prepare the loopback-only runtime and queue any missed static refresh."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from transit.services.feed_registry import ensure_official_feed_registry
from transit.services.local_bootstrap import static_refresh_is_due
from transit.tasks import refresh_static_gtfs


class Command(BaseCommand):
    """Seed official feeds and queue a local static catch-up exactly when needed."""

    help = "Initialise the local runtime and queue a due GTFS static refresh."

    def handle(self, *args: object, **options: object) -> str:
        del args, options
        if not settings.LOCAL_ONLY:
            raise CommandError("bootstrap_local is available only when DJANGO_LOCAL_ONLY=true.")

        feeds = ensure_official_feed_registry()
        if not static_refresh_is_due(timezone.now()):
            return self.style.SUCCESS(
                f"Registered {len(feeds)} official GTFS feeds; refresh is current."
            )

        refresh_static_gtfs.delay()
        return self.style.SUCCESS(
            f"Registered {len(feeds)} official GTFS feeds; queued static refresh."
        )
