"""Download, archive, validate, and activate official GTFS static feeds."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from transit.services.r2_archive import ArchiveConfigurationError, R2ArchiveStore
from transit.services.static_refresh import StaticFeedRefresher


class Command(BaseCommand):
    """Perform the serial 4-requests-per-minute static refresh workflow."""

    help = "Refresh one or all official GTFS static feeds through R2 archiving."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--feed", help="Optional official feed slug to refresh.")

    def handle(self, *args: object, **options: object) -> str:
        del args
        feed_option = options.get("feed")
        if feed_option is not None and not isinstance(feed_option, str):
            raise CommandError("Feed option must be a string.")
        try:
            refresher = StaticFeedRefresher(R2ArchiveStore.from_environment())
            results = refresher.refresh_all(feed_option)
        except (ArchiveConfigurationError, ValueError) as error:
            raise CommandError(str(error)) from error

        active_count = sum(result.status == "active" for result in results)
        failed_count = len(results) - active_count
        result_lines = [
            f"{result.feed_slug}: {result.status}" for result in results
        ]
        message = "\n".join(
            [
                f"Static refresh completed: {active_count} active, {failed_count} failed.",
                *result_lines,
            ]
        )
        return self.style.SUCCESS(message) if failed_count == 0 else self.style.WARNING(message)
