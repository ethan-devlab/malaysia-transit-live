"""The complete official Malaysian GTFS feed registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from transit.models import TransitFeed

STATIC_BASE_URL: Final = "https://api.data.gov.my/gtfs-static"
REALTIME_BASE_URL: Final = "https://api.data.gov.my/gtfs-realtime/vehicle-position"


@dataclass(frozen=True)
class FeedDefinition:
    """One feed's official URLs and its realtime-poll priority."""

    slug: str
    display_name: str
    static_source_url: str
    realtime_source_url: str = ""
    realtime_priority: int = 0
    operator_key: str = ""
    operator_name: str = ""
    region_key: str = ""
    region_name: str = ""

    def __post_init__(self) -> None:
        metadata = _dashboard_metadata(self.slug, self.display_name)
        for field_name, value in metadata.items():
            if not getattr(self, field_name):
                object.__setattr__(self, field_name, value)


def _dashboard_metadata(slug: str, display_name: str) -> dict[str, str]:
    if slug == "ktmb":
        return {
            "operator_key": "ktmb",
            "operator_name": "KTMB",
            "region_key": "national",
            "region_name": "Malaysia",
        }
    if slug.startswith("rapid-"):
        region_key = "kuala-lumpur"
        if "penang" in slug:
            region_key = "penang"
        elif "kuantan" in slug:
            region_key = "kuantan"
        region_name = {"penang": "Penang", "kuantan": "Kuantan", "kuala-lumpur": "Kuala Lumpur"}[region_key]
        operator_key = {"penang": "rapid-penang", "kuantan": "rapid-kuantan", "kuala-lumpur": "rapid-kl"}[region_key]
        operator_name = {"penang": "Rapid Penang", "kuantan": "Rapid Kuantan", "kuala-lumpur": "Rapid KL"}[region_key]
        return {
            "operator_key": operator_key,
            "operator_name": operator_name,
            "region_key": region_key,
            "region_name": region_name,
        }
    if slug.startswith("mybas-"):
        return {
            "operator_key": "bas-my",
            "operator_name": "BAS.MY",
            "region_key": slug.removeprefix("mybas-"),
            "region_name": display_name.removeprefix("BAS.MY "),
        }
    return {
        "operator_key": slug,
        "operator_name": display_name,
        "region_key": "unknown",
        "region_name": "Unclassified",
    }


OFFICIAL_FEEDS: Final[tuple[FeedDefinition, ...]] = (
    FeedDefinition(
        slug="ktmb",
        display_name="Keretapi Tanah Melayu Berhad",
        static_source_url=f"{STATIC_BASE_URL}/ktmb",
        realtime_source_url=f"{REALTIME_BASE_URL}/ktmb",
        realtime_priority=1,
    ),
    FeedDefinition(
        slug="rapid-bus-kl",
        display_name="Rapid Bus Kuala Lumpur",
        static_source_url=f"{STATIC_BASE_URL}/prasarana?category=rapid-bus-kl",
        realtime_source_url=f"{REALTIME_BASE_URL}/prasarana?category=rapid-bus-kl",
        realtime_priority=2,
    ),
    FeedDefinition(
        slug="rapid-bus-mrtfeeder",
        display_name="Rapid Bus MRT Feeder",
        static_source_url=f"{STATIC_BASE_URL}/prasarana?category=rapid-bus-mrtfeeder",
        realtime_source_url=f"{REALTIME_BASE_URL}/prasarana?category=rapid-bus-mrtfeeder",
        realtime_priority=3,
    ),
    FeedDefinition(
        slug="rapid-rail-kl",
        display_name="Rapid Rail Kuala Lumpur",
        static_source_url=f"{STATIC_BASE_URL}/prasarana?category=rapid-rail-kl",
    ),
    FeedDefinition(
        slug="rapid-bus-penang",
        display_name="Rapid Bus Penang",
        static_source_url=f"{STATIC_BASE_URL}/prasarana?category=rapid-bus-penang",
        realtime_source_url=f"{REALTIME_BASE_URL}/prasarana?category=rapid-bus-penang",
    ),
    FeedDefinition(
        slug="rapid-bus-kuantan",
        display_name="Rapid Bus Kuantan",
        static_source_url=f"{STATIC_BASE_URL}/prasarana?category=rapid-bus-kuantan",
        realtime_source_url=f"{REALTIME_BASE_URL}/prasarana?category=rapid-bus-kuantan",
    ),
    FeedDefinition(
        "mybas-kangar",
        "BAS.MY Kangar",
        f"{STATIC_BASE_URL}/mybas-kangar",
        f"{REALTIME_BASE_URL}/mybas-kangar",
    ),
    FeedDefinition(
        "mybas-alor-setar",
        "BAS.MY Alor Setar",
        f"{STATIC_BASE_URL}/mybas-alor-setar",
        f"{REALTIME_BASE_URL}/mybas-alor-setar",
    ),
    FeedDefinition(
        "mybas-kota-bharu",
        "BAS.MY Kota Bharu",
        f"{STATIC_BASE_URL}/mybas-kota-bharu",
        f"{REALTIME_BASE_URL}/mybas-kota-bharu",
    ),
    FeedDefinition(
        "mybas-kuala-terengganu",
        "BAS.MY Kuala Terengganu",
        f"{STATIC_BASE_URL}/mybas-kuala-terengganu",
        f"{REALTIME_BASE_URL}/mybas-kuala-terengganu",
    ),
    FeedDefinition(
        "mybas-ipoh",
        "BAS.MY Ipoh",
        f"{STATIC_BASE_URL}/mybas-ipoh",
        f"{REALTIME_BASE_URL}/mybas-ipoh",
    ),
    FeedDefinition(
        "mybas-seremban-a",
        "BAS.MY Seremban A",
        f"{STATIC_BASE_URL}/mybas-seremban-a",
        f"{REALTIME_BASE_URL}/mybas-seremban-a",
    ),
    FeedDefinition(
        "mybas-seremban-b",
        "BAS.MY Seremban B",
        f"{STATIC_BASE_URL}/mybas-seremban-b",
        f"{REALTIME_BASE_URL}/mybas-seremban-b",
    ),
    FeedDefinition(
        "mybas-melaka",
        "BAS.MY Melaka",
        f"{STATIC_BASE_URL}/mybas-melaka",
        f"{REALTIME_BASE_URL}/mybas-melaka",
    ),
    FeedDefinition(
        "mybas-johor",
        "BAS.MY Johor Bahru",
        f"{STATIC_BASE_URL}/mybas-johor",
        f"{REALTIME_BASE_URL}/mybas-johor",
    ),
    FeedDefinition(
        "mybas-kuching",
        "BAS.MY Kuching",
        f"{STATIC_BASE_URL}/mybas-kuching",
        f"{REALTIME_BASE_URL}/mybas-kuching",
    ),
)


def ensure_official_feed_registry() -> list[TransitFeed]:
    """Upsert the full official registry without overwriting operational version history."""
    feeds: list[TransitFeed] = []
    for definition in OFFICIAL_FEEDS:
        feed, _ = TransitFeed.objects.update_or_create(
            slug=definition.slug,
            defaults={
                "display_name": definition.display_name,
                "static_source_url": definition.static_source_url,
                "realtime_source_url": definition.realtime_source_url,
                "realtime_priority": definition.realtime_priority,
                "is_realtime_enabled": bool(definition.realtime_source_url),
                "operator_key": definition.operator_key,
                "operator_name": definition.operator_name,
                "region_key": definition.region_key,
                "region_name": definition.region_name,
            },
        )
        feeds.append(feed)
    return feeds
