"""Upsert the full official data.gov.my GTFS feed registry."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from transit.services.feed_registry import ensure_official_feed_registry


class Command(BaseCommand):
    """Register every official static feed and known vehicle-position endpoint."""

    help = "Upsert the official Malaysian GTFS feed registry."

    def handle(self, *args: object, **options: object) -> str:
        del args, options
        feeds = ensure_official_feed_registry()
        return self.style.SUCCESS(f"Registered {len(feeds)} official GTFS feeds.")
