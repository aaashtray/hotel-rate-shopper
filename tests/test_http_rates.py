"""All invented hotel and rate data below are explicitly synthetic."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from rate_shopper.batch import write_batch
from rate_shopper.connectors.http_rates import capture, request_spec
from rate_shopper.domain.api_capture import ApiCapture
from rate_shopper.domain.capture import BatchConfig, HotelTarget
from rate_shopper.domain.models import Platform, Status
from rate_shopper.extraction.http_rates import capture_status, extract, money
from rate_shopper.quality.gates import issues
from rate_shopper.reporting.statistics import preliminary_scenario
from rate_shopper.scenarios.weekend import weekend_scenario

NOW = datetime(2026, 11, 25, 6, tzinfo=UTC)
SCENARIO = weekend_scenario(NOW)
HOTEL = HotelTarget(id="synthetic", name="SYNTHETIC", aliases=("SYNTHETIC",), urls={
    Platform.OTELLO: "https://otello.ru/hotel/123",
    Platform.OSTROVOK: "https://ostrovok.ru/hotel/russia/moscow/mid123/synthetic/",
})


def fixture(platform: Platform, body: dict[str, Any]) -> ApiCapture:
    endpoint, params = request_spec(HOTEL, platform, SCENARIO)
    return ApiCapture(
        provenance="synthetic", platform=platform, hotel_id=HOTEL.id, checked_at=NOW,
        url=HOTEL.urls[platform], requested_url=HOTEL.urls[platform], title="SYNTHETIC",
        endpoint=endpoint, request_parameters=params, scenario=SCENARIO,
        response_text=json.dumps(body), http_status=200,
    )


def otello() -> dict[str, Any]:
    return {"result": {"id": "123", "booking_params": {
        "checkin": "2026-11-27T14:00", "checkout": "2026-11-29T12:00",
        "guest_groups": [{"adults": 2}],
    }, "rooms": [{"name": "SYNTHETIC room", "rate_plans": [{
        "total": {"price": "10000.25", "currency": "RUB"},
        "average_per_night": {"price": "5000.13", "currency": "RUB"},
        "meal_type": {"code": "BreakFast", "name": "Завтрак"},
        "cancellation": {"rules": [{"type": "no_refund"}]},
        "payment_method": "credit_card", "taxes": {"items": []},
    }]}]}}


def ostrovok() -> dict[str, Any]:
    return {"ota_hotel_id": "synthetic", "master_id": 123, "rates": [{
        "room_name": "SYNTHETIC room", "occupancy": 2,
        "rooms": [{"bedding_data": ["double"]}], "meal": ["nomeal"],
        "payment_options": {"payment_types": [{"amount": "10000.25", "currency_code": "RUB",
                                              "is_enabled": True, "type": "now"}]},
        "cancellation_info": {"policies": [{"penalty": {"amount": "10000.25"}}]},
        "display_prices": {"taxes_not_included_now": [], "taxes_not_included_later": []},
    }, {
        "room_name": "SYNTHETIC refundable", "occupancy": 2, "rooms": [{}], "meal": ["nomeal"],
        "payment_options": {"payment_types": [{"amount": "12000", "currency_code": "RUB",
                                              "is_enabled": True, "type": "now"}]},
        "cancellation_info": {"free_cancellation_before": "2026-11-26T12:00:00Z"},
    }]}


@pytest.mark.parametrize(("day", "start", "end"), [
    ("2026-11-30", "2026-12-04", "2026-12-06"),
    ("2026-12-14", "2026-12-18", "2026-12-20"),
    ("2026-12-28", "2027-01-01", "2027-01-03"),
    ("2026-11-27", "2026-12-04", "2026-12-06"),
])
def test_monday_weekends_and_year_boundary(day: str, start: str, end: str) -> None:
    scenario = weekend_scenario(datetime.fromisoformat(day).replace(tzinfo=UTC))
    assert (str(scenario.checkin), str(scenario.checkout)) == (start, end)
    assert scenario.adults == 2 and scenario.rooms == 1


def test_stay_total_and_cents_never_derived_from_rounded_night() -> None:
    result = extract(fixture(Platform.OTELLO, otello()), SCENARIO, HOTEL, "obs")
    assert result[0].public_total == Decimal("10000.25")
    assert result[0].meal_plan == "breakfast"
    assert result[0].observed_scenario == SCENARIO


def test_no_total_no_offer() -> None:
    data = otello()
    del data["result"]["rooms"][0]["rate_plans"][0]["total"]
    assert not extract(fixture(Platform.OTELLO, data), SCENARIO, HOTEL, "obs")


def test_cancellation_stays_with_its_rate() -> None:
    result = extract(fixture(Platform.OSTROVOK, ostrovok()), SCENARIO, HOTEL, "obs")
    assert [(o.public_total, o.cancellation_type) for o in result] == [
        (Decimal("10000.25"), "non_refundable"), (Decimal("12000"), "free"),
    ]
    assert result[0].cancellation_deadline is None
    assert result[1].cancellation_deadline is not None


def test_request_bound_scenario_is_never_promoted_to_strict() -> None:
    result = extract(fixture(Platform.OSTROVOK, ostrovok()), SCENARIO, HOTEL, "obs")[0]
    assert preliminary_scenario(result) == SCENARIO
    assert result.observed_scenario is None
    assert "page/form scenario unverified" in issues(result, SCENARIO)


@pytest.mark.parametrize("mutation", ["hotel", "checkout", "adults", "rooms"])
def test_otello_mismatch_rejected(mutation: str) -> None:
    data = otello()
    if mutation == "hotel":
        data["result"]["id"] = "999"
    elif mutation == "checkout":
        data["result"]["booking_params"]["checkout"] = "2026-11-30T12:00"
    elif mutation == "adults":
        data["result"]["booking_params"]["guest_groups"] = [{"adults": 1}]
    else:
        data["result"]["booking_params"]["guest_groups"] = [{"adults": 2}, {"adults": 2}]
    assert not extract(fixture(Platform.OTELLO, data), SCENARIO, HOTEL, "obs")


def test_disabled_payment_and_foreign_currency_are_excluded() -> None:
    data = ostrovok()
    data["rates"][0]["payment_options"]["payment_types"][0]["is_enabled"] = False
    data["rates"][1]["payment_options"]["payment_types"][0]["currency_code"] = "USD"
    assert not extract(fixture(Platform.OSTROVOK, data), SCENARIO, HOTEL, "obs")


def test_missing_and_empty_responses_are_not_sold_out() -> None:
    for body in ({}, {"ota_hotel_id": "synthetic", "master_id": 123, "rates": []}):
        assert capture_status(fixture(Platform.OSTROVOK, body), SCENARIO, HOTEL) != Status.SOLD_OUT


def test_non_ruble_response_is_a_scenario_mismatch() -> None:
    data = ostrovok()
    for rate in data["rates"]:
        rate["payment_options"]["payment_types"][0]["currency_code"] = "USD"
    assert capture_status(fixture(Platform.OSTROVOK, data), SCENARIO, HOTEL) == (
        Status.SCENARIO_MISMATCH
    )


def test_instalments_are_not_public_card_price() -> None:
    data = otello()
    data["result"]["rooms"][0]["rate_plans"][0]["payment_method"] = "buy_now_pay_later"
    result = extract(fixture(Platform.OTELLO, data), SCENARIO, HOTEL, "obs")[0]
    assert result.public_total is None and result.access_type == "bank"
    assert result.bank_product_total == Decimal("10000.25")


@pytest.mark.parametrize(("method", "timing"), [("front_desk", "at_hotel"),
                                               ("credit_card", "now")])
def test_payment_methods_follow_source_labels(method: str, timing: str) -> None:
    data = otello()
    data["result"]["rooms"][0]["rate_plans"][0]["payment_method"] = method
    result = extract(fixture(Platform.OTELLO, data), SCENARIO, HOTEL, "obs")[0]
    assert result.public_total == Decimal("10000.25")
    assert result.payment_timing == timing
    assert result.special_payment_product is None


def test_rate_limit_stops_without_retry() -> None:
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, text="Rate limited")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = capture(client, HOTEL, Platform.OTELLO, SCENARIO)
    assert result.collection_error == Status.RATE_LIMITED
    assert len(calls) == 1


@pytest.mark.parametrize("value", [float("nan"), 1.5, "NaN", "Infinity", "-1", "0", True,
                                   "1e1000", "1.001"])
def test_invalid_money(value: Any) -> None:
    assert money(value) is None


def test_missing_capture_link_uses_current_stay(tmp_path: Path) -> None:
    hotel = HOTEL.model_copy(update={"urls": {Platform.OZON:
        "https://ozon.ru/travel/hotels/product/synthetic-123/"
        "?checkIn=2026-01-01&checkOut=2026-01-03"}})
    config = BatchConfig(hotels=(hotel,), platforms=(Platform.OZON,))
    config_path, scenario_path = tmp_path / "hotels.json", tmp_path / "scenario.json"
    config_path.write_text(config.model_dump_json())
    scenario_path.write_text(SCENARIO.model_dump_json())
    captures = tmp_path / "captures"
    captures.mkdir()
    result = write_batch(captures, config_path, scenario_path, tmp_path / "report")
    observation = result["observations"][0]
    assert observation["status"] == "UNKNOWN"
    assert "checkIn=2026-11-27" in observation["source_url"]
    assert "checkOut=2026-11-29" in observation["source_url"]
