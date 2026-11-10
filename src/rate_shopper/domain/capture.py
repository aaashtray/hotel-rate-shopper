from datetime import datetime
from typing import Literal

from pydantic import Field

from rate_shopper.domain.models import HotelRegistration, Model, Platform


class CapturedRate(Model):
    text: str
    price: str | None = None
    meal: str | None = None
    cancellation: str | None = None
    payment_selected: str | None = None


class CapturedRoom(Model):
    text: str
    rates: tuple[CapturedRate, ...]


class Supplement(Model):
    card: int
    rate: int
    kind: str
    text: str


class BrowserCapture(Model):
    provenance: Literal["observed", "synthetic"]
    platform: Platform
    checked_at: datetime
    url: str
    requested_url: str | None = None
    title: str
    snapshot: str
    cards: tuple[CapturedRoom, ...]
    supplements: tuple[Supplement, ...] = ()
    capture_method: str = "browser_dom"
    coverage: Literal["visible", "expanded"] = "visible"
    collection_error: str | None = None
    screenshot_path: str | None = None
    authorization_state: Literal["anonymous", "authenticated", "unknown"] = "unknown"


class HotelTarget(Model):
    id: str
    name: str
    aliases: tuple[str, ...]
    urls: dict[Platform, str]
    address_tokens: tuple[str, ...] = ()
    country: str = "Россия"
    geo: str = "Москва"
    location_aliases: tuple[str, ...] = ()
    mapping_notes: dict[Platform, str] = Field(default_factory=dict)
    stars: int | None = Field(default=None, ge=1, le=5)
    stars_source: str | None = None
    registrations: tuple[HotelRegistration, ...] = ()


class BatchConfig(Model):
    hotels: tuple[HotelTarget, ...]
    platforms: tuple[Platform, ...] = (Platform.OTELLO, Platform.OZON)
    excluded_platforms: dict[str, str] = Field(default_factory=dict)
