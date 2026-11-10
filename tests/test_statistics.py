"""Synthetic analytical cases; no invented inputs enter observed reports."""
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from rate_shopper.domain.capture import BatchConfig, HotelTarget
from rate_shopper.domain.models import Fixture, Offer, Platform
from rate_shopper.reporting.statistics import preliminary_statistics, verified_statistics

FIXTURE = Fixture.model_validate_json(
    (Path(__file__).parent / "fixtures/synthetic/reference.json").read_bytes()
)
TARGET = HotelTarget(id="savoy", name="Synthetic Savoy", aliases=("Synthetic",), urls={})
CONFIG = BatchConfig(hotels=(TARGET,), platforms=(Platform.OTELLO, Platform.OZON))
A = next(o for o in FIXTURE.offers if o.id == "savoy-otello")
B = next(o for o in FIXTURE.offers if o.id == "savoy-ozon")


def row(offers: list[Offer], config: BatchConfig = CONFIG) -> dict[str, Any]:
    result: dict[str, Any] = preliminary_statistics(offers, config, [])["rows"][0]
    return result


def test_minimum_is_one_hotel_competitor_pair_with_competitor_denominator() -> None:
    a = A.model_copy(update={"public_total": Decimal("120.50")})
    b = B.model_copy(update={"public_total": Decimal("100")})
    expensive = b.model_copy(update={"id": "expensive", "public_total": Decimal("150")})
    result = preliminary_statistics([a, b, expensive], CONFIG, [])
    assert len(result["rows"]) == 1
    r = result["rows"][0]
    assert r["absolute_gap"] == "20.50"
    assert r["percent_gap"] == "20.50"
    assert r["outcome"] == "loss"
    assert r["competitor_offer_id"] == b.id


@pytest.mark.parametrize("access", ["bank", "personal", "member", "mobile"])
def test_conditional_prices_never_enter_public_statistics(access: str) -> None:
    conditional = B.model_copy(update={"access_type": access, "public_total": Decimal("1")})
    assert row([A, conditional])["percent_gap"] is None
    assert row([A, B, conditional])["competitor_offer_id"] == B.id


def test_unknown_authentication_is_not_public_evidence() -> None:
    b = B.model_copy(update={"authorization_required": None})
    assert row([A, b])["reason"] == "no_competitor_public_price"


def test_known_extra_fees_exclude_pair_instead_of_selecting_expensive_alternative() -> None:
    cheap = B.model_copy(update={"public_total": Decimal("10"), "taxes_included": False,
                                "source_fragments": {"additional_fees": "+ 800 $"}})
    expensive = B.model_copy(update={"id": "expensive"})
    r = row([A, cheap, expensive])
    assert r["reason"] == "separate_fees"
    assert r["percent_gap"] is None


def test_explicit_mapping_dispute_blocks_exploratory_gap() -> None:
    config = CONFIG.model_copy(update={"hotels": (TARGET.model_copy(
        update={"mapping_notes": {Platform.OZON: "Different addresses"}}
    ),)})
    assert row([A, B], config)["reason"] == "mapping_disputed"


def test_scenario_mismatch_blocks_exploratory_gap() -> None:
    b = B.model_copy(update={"observed_scenario": FIXTURE.scenario.model_copy(
        update={"adults": 1}
    )})
    assert row([A, b])["reason"] == "scenario_mismatch"


def test_verified_mode_does_not_promote_preliminary_results() -> None:
    assert row([A, B])["percent_gap"] is not None
    assert verified_statistics([A, B], []) == []


def test_equal_prices_are_ties_and_cheaper_otello_is_negative() -> None:
    assert row([A, B.model_copy(update={"public_total": A.public_total})])["outcome"] == "tie"
    r = row([A, B.model_copy(update={"public_total": Decimal("60000")})])
    assert r["percent_gap"] == "-50.00"
    assert r["outcome"] == "win"
