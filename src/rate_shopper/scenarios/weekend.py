"""Monday collection compares the following Friday–Sunday, in Moscow time."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rate_shopper.domain.models import Scenario

MOSCOW = ZoneInfo("Europe/Moscow")


def weekend_scenario(now: datetime, *, nights: int = 2) -> Scenario:
    if now.tzinfo is None:
        raise ValueError("Collection time must have a timezone")
    today = now.astimezone(MOSCOW).date()
    days = (4 - today.weekday()) % 7
    # A manual Friday run targets next Friday, never a same-day/past check-in.
    start = today + timedelta(days=days or 7)
    return Scenario(
        id=f"weekend-{start}-{nights}n-2a", checkin=start,
        checkout=start + timedelta(days=nights), adults=2, rooms=1,
        created_at=now,
    )
