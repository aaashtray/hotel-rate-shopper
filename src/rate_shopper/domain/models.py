import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, decimal_places=2)]
Confidence = Annotated[Decimal, Field(ge=0, le=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Platform(StrEnum):
    OTELLO = "otello"
    YANDEX = "yandex_travel"
    OZON = "ozon_travel"
    OSTROVOK = "ostrovok"


class Status(StrEnum):
    AVAILABLE = "AVAILABLE"
    SOLD_OUT = "SOLD_OUT"
    HOTEL_NOT_FOUND = "HOTEL_NOT_FOUND"
    PRICE_NOT_EXPOSED = "PRICE_NOT_EXPOSED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CAPTCHA = "CAPTCHA"
    RATE_LIMITED = "RATE_LIMITED"
    CONNECTOR_ERROR = "CONNECTOR_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    SCENARIO_MISMATCH = "SCENARIO_MISMATCH"
    UNKNOWN = "UNKNOWN"


class Scenario(Model):
    id: str
    checkin: date
    checkout: date
    adults: int = Field(gt=0)
    children_ages: tuple[Annotated[int, Field(ge=0, le=17)], ...] = ()
    rooms: int = Field(gt=0)
    currency: str = "RUB"
    created_at: datetime

    @model_validator(mode="after")
    def valid_dates(self) -> "Scenario":
        if self.checkout <= self.checkin:
            raise ValueError("checkout must be after checkin")
        if self.currency != "RUB":
            raise ValueError("MVP supports RUB only")
        return self

    @property
    def nights(self) -> int:
        return (self.checkout - self.checkin).days

    def signature(self) -> tuple[Any, ...]:
        return (
            self.checkin,
            self.checkout,
            self.adults,
            tuple(sorted(self.children_ages)),
            self.rooms,
            self.currency,
        )


class HotelRegistration(Model):
    registry: str
    country: str
    registration_id: str
    source_url: str
    source_text: str
    verification_status: Literal["user_supplied", "source_observed", "registry_verified"]
    checked_at: datetime | None = None

    @field_validator("registration_id", mode="before")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        value = value.strip().upper()
        if re.fullmatch(r"[CС]\d{12}", value):
            return "С" + value[1:]
        return value

    @model_validator(mode="after")
    def validate_registration(self) -> "HotelRegistration":
        if self.registry == "ru_accommodation" and not re.fullmatch(
            r"С\d{12}", self.registration_id
        ):
            raise ValueError("Invalid Russian accommodation registration ID")
        if self.verification_status != "user_supplied" and self.checked_at is None:
            raise ValueError("Observed registration requires checked_at")
        return self

    def key(self) -> tuple[str, str, str]:
        return self.country, self.registry, self.registration_id


class SourceMapping(Model):
    platform: Platform
    source_id: str
    verified: bool = False


class HotelEntity(Model):
    canonical_id: str
    canonical_name: str
    city: str
    address: str | None = None
    source_mappings: tuple[SourceMapping, ...] = ()
    registrations: tuple[HotelRegistration, ...] = ()


class RawObservation(Model):
    id: str
    run_id: str
    platform: Platform
    scenario_id: str
    requested_url: str | None = None
    final_url: str | None = None
    checked_at: datetime
    http_status: int | None = None
    capture_method: str
    raw_html_path: str | None = None
    raw_json_paths: tuple[str, ...] = ()
    page_text_path: str | None = None
    screenshot_path: str | None = None
    auth_state: str
    captcha_detected: bool = False
    connector_version: str
    content_hash: str
    error_code: str | None = None
    error_message: str | None = None


class Offer(Model):
    id: str
    observation_id: str
    platform: Platform
    scenario_id: str
    hotel_canonical_id: str | None
    hotel_source_id: str | None = None
    registration: HotelRegistration | None = None
    hotel_name_raw: str
    room_name_raw: str | None = None
    room_category_normalized: str | None = None
    bed_type: str | None = None
    room_area_m2: Decimal | None = Field(default=None, gt=0)
    meal_plan: Literal["none", "breakfast", "half_board", "full_board", "all_inclusive"] | None = (
        None
    )
    cancellation_type: Literal["free", "non_refundable"] | None = None
    cancellation_deadline: datetime | None = None
    payment_timing: Literal["at_hotel", "now", "later"] | None = None
    public_total: Money | None = None
    member_total: Money | None = None
    bank_product_total: Money | None = None
    mobile_total: Money | None = None
    crossed_out_total: Money | None = None
    taxes_total: Money | None = None
    taxes_included: bool | None = None
    currency: str = "RUB"
    availability_status: Status
    authorization_required: bool | None = None
    loyalty_program: str | None = None
    special_payment_product: str | None = None
    special_conditions: tuple[str, ...] = ()
    source_url: str | None = None
    source_fragments: dict[str, str]
    extraction_confidence: Confidence
    price_basis: Literal["stay_total", "night"] | None = None
    access_type: Literal["public", "member", "bank", "mobile", "corporate", "personal"] | None = (
        None
    )
    observed_scenario: Scenario | None = None
    url_scenario: Scenario | None = None

    @field_validator(
        "public_total",
        "member_total",
        "bank_product_total",
        "mobile_total",
        "crossed_out_total",
        "taxes_total",
        mode="before",
    )
    @classmethod
    def no_float(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError("Money must be a decimal string, Decimal or integer")
        return value


class OfferMatch(Model):
    id: str
    scenario_id: str
    hotel_canonical_id: str | None
    reference_offer_id: str
    competitor_offer_id: str
    match_quality: str
    match_confidence: Confidence
    differences: tuple[str, ...]
    absolute_gap: Decimal | None
    percent_gap: Decimal | None
    manual_review_required: bool
    matcher_version: str = "rules-1"
    created_at: datetime


class Fixture(Model):
    provenance: str
    assumptions: tuple[str, ...]
    scenario: Scenario
    hotels: tuple[HotelEntity, ...]
    offers: tuple[Offer, ...]
    expected_observations: int = Field(gt=0)

    @model_validator(mode="after")
    def consistent(self) -> "Fixture":
        if self.provenance != "synthetic":
            raise ValueError("This importer accepts synthetic domain fixtures only")
        ids = [o.id for o in self.offers]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate offer IDs")
        if len({o.observation_id for o in self.offers}) != len(self.offers):
            raise ValueError("M1 fixtures require one offer per observation")
        if len(self.offers) > self.expected_observations:
            raise ValueError("More observations than expected")
        hotel_ids = {h.canonical_id for h in self.hotels}
        if any(
            o.hotel_canonical_id not in hotel_ids
            for o in self.offers
            if o.hotel_canonical_id is not None
        ):
            raise ValueError("Unregistered canonical hotel")
        return self
