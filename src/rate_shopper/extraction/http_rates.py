"""Deterministic normalization of one hotel's anonymous HTTP response."""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from rate_shopper.connectors.http_rates import source_id
from rate_shopper.domain.api_capture import ApiCapture
from rate_shopper.domain.capture import HotelTarget
from rate_shopper.domain.models import Offer, Platform, Scenario, Status
from rate_shopper.extraction.browser import bed, category


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, (bool, float)):
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
            return None
    except InvalidOperation:
        return None
    return amount


def payload(capture: ApiCapture) -> dict[str, Any]:
    data = json.loads(capture.response_text, parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def echoed_scenario(data: dict[str, Any], scenario: Scenario) -> Scenario | None:
    try:
        groups = data["guest_groups"]
        if len(groups) != 1:
            return None
        return Scenario.model_validate({
            **scenario.model_dump(), "checkin": data["checkin"][:10],
            "checkout": data["checkout"][:10], "adults": groups[0]["adults"],
            "children_ages": groups[0].get("children", []), "rooms": len(groups),
        })
    except (KeyError, TypeError, ValueError):
        return None


def capture_status(capture: ApiCapture, scenario: Scenario, hotel: HotelTarget) -> Status:
    if capture.collection_error:
        try:
            return Status(capture.collection_error)
        except ValueError:
            return Status.CONNECTOR_ERROR
    if capture.http_status != 200:
        return Status.CONNECTOR_ERROR
    if capture.hotel_id != hotel.id:
        return Status.UNKNOWN
    if capture.scenario.signature() != scenario.signature():
        return Status.SCENARIO_MISMATCH
    try:
        data = payload(capture)
        expected_id = source_id(hotel, capture.platform)
        params = capture.request_parameters
        if capture.platform == Platform.OTELLO:
            result = data["result"]
            if str(result["id"]) != expected_id:
                return Status.UNKNOWN
            observed = echoed_scenario(result.get("booking_params", {}), scenario)
            if not observed or observed.signature() != scenario.signature():
                return Status.SCENARIO_MISMATCH
            if "rooms" not in result or not isinstance(result["rooms"], list):
                return Status.PARSE_ERROR
            return Status.AVAILABLE if result["rooms"] else Status.SOLD_OUT
        if capture.platform != Platform.OSTROVOK:
            return Status.CONNECTOR_ERROR
        if (params.get("arrival_date") != str(scenario.checkin)
                or params.get("departure_date") != str(scenario.checkout)
                or params.get("paxes") != [{"adults": scenario.adults, "child_ages": []}]
                or params.get("currency") != "RUB" or params.get("hotel") != expected_id
                or params.get("guru_auth_prices_enabled") is not False):
            return Status.SCENARIO_MISMATCH
        if data.get("ota_hotel_id") != expected_id:
            return Status.UNKNOWN
        mid = re.search(r"/mid(\d+)/", urlsplit(hotel.urls[capture.platform]).path)
        if mid and str(data.get("master_id")) != mid[1]:
            return Status.UNKNOWN
        if "rates" not in data or not isinstance(data["rates"], list):
            return Status.PRICE_NOT_EXPOSED
        currencies = {
            payment.get("currency_code") for rate in data["rates"]
            for payment in (rate.get("payment_options") or {}).get("payment_types", [])
            if payment.get("is_enabled") is True and payment.get("currency_code")
        }
        if currencies and "RUB" not in currencies:
            return Status.SCENARIO_MISMATCH
        # An empty internal response does not itself prove SOLD_OUT.
        return Status.AVAILABLE if data["rates"] else Status.PRICE_NOT_EXPOSED
    except (KeyError, TypeError, ValueError):
        return Status.PARSE_ERROR


def deadline(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


def fee_text(items: list[dict[str, Any]], translations: dict[str, str] | None = None) -> str:
    labels = translations or {}
    return "; ".join(
        f"{labels.get(str(item.get('name')), str(item.get('name', 'Сбор')))}: "
        f"{item.get('amount', '?')} {item.get('currency', '')}"
        for item in items
    )


def cancellation(
    raw: dict[str, Any], platform: Platform, total: Decimal, now: datetime,
) -> tuple[str | None, datetime | None]:
    if platform == Platform.OTELLO:
        for rule in raw.get("rules", []):
            end = deadline(rule.get("ends_at"))
            start = deadline(rule.get("starts_at"))
            if start and start > now:
                continue
            if end and end <= now:
                continue
            if rule.get("type") in {"full_refund_until_deadline", "full_refund"} and end:
                return "free", end
            if rule.get("type") in {"non_refundable", "no_refund"}:
                return "non_refundable", None
    else:
        end = deadline(raw.get("free_cancellation_before"))
        if end and end > now:
            return "free", end
        for rule in raw.get("policies", []):
            start, end = deadline(rule.get("start_at")), deadline(rule.get("end_at"))
            if rule.get("start_at") and not start or rule.get("end_at") and not end:
                continue
            if start and start > now or end and end <= now:
                continue
            if money((rule.get("penalty") or {}).get("amount")) == total:
                return "non_refundable", None
    return None, None


def offer(
    capture: ApiCapture, hotel: HotelTarget, observation_id: str, index: str,
    *, room: str, total: Decimal, meal: str | None, cancel: str | None,
    cancel_at: datetime | None, timing: str | None, bed_type: str | None,
    fragments: dict[str, str], taxes: bool | None, conditional: str | None = None,
    observed: Scenario | None = None,
) -> Offer:
    access = "bank" if conditional else "public"
    fields: dict[str, Any] = dict(
        id=f"api-{observation_id[:20]}-{index}", observation_id=observation_id,
        platform=capture.platform, scenario_id=capture.scenario.id,
        hotel_canonical_id=hotel.id, hotel_source_id=source_id(hotel, capture.platform),
        hotel_name_raw=hotel.name, room_name_raw=room,
        room_category_normalized=category(room), bed_type=bed_type, meal_plan=meal,
        cancellation_type=cancel, cancellation_deadline=cancel_at, payment_timing=timing,
        public_total=None if conditional else total,
        bank_product_total=total if conditional else None, currency="RUB",
        taxes_included=taxes, availability_status=Status.AVAILABLE,
        authorization_required=bool(conditional), access_type=access,
        price_basis="stay_total", source_url=capture.url,
        special_payment_product=conditional,
        observed_scenario=observed, url_scenario=capture.scenario,
        extraction_confidence=Decimal("1"),
    )
    evidence = {
        "hotel_canonical_id": "Existing mapped source ID matched the response",
        "availability_status": "Positive enabled bookable offer in HTTP response",
        "price_basis": "Explicit whole-stay total; average_per_night was not multiplied",
        "access_type": access, "authorization_required": str(bool(conditional)),
        "room_category_normalized": room, **fragments,
    }
    for key in ("meal_plan", "cancellation_type", "cancellation_deadline", "payment_timing",
                "bed_type", "taxes_included"):
        if fields.get(key) is not None:
            evidence.setdefault(key, str(fields[key]))
    if observed:
        evidence["observed_scenario"] = fragments["scenario_validation"]
    return Offer.model_validate({**fields, "source_fragments": evidence})


def extract(
    capture: ApiCapture, scenario: Scenario, hotel: HotelTarget, observation_id: str,
) -> list[Offer]:
    if capture_status(capture, scenario, hotel) != Status.AVAILABLE:
        return []
    data = payload(capture)
    offers = []
    if capture.platform == Platform.OTELLO:
        result = data["result"]
        observed = echoed_scenario(result["booking_params"], scenario)
        for ri, room in enumerate(result["rooms"]):
            for pi, rate in enumerate(room.get("rate_plans", [])):
                total_data = rate.get("total") or {}
                total = money(total_data.get("price"))
                if total is None or total_data.get("currency") != "RUB":
                    continue
                meal_raw = rate.get("meal_type") or {}
                meal = {"RoomOnly": "none", "Breakfast": "breakfast", "BreakFast": "breakfast",
                        "HalfBoard": "half_board",
                        "FullBoard": "full_board", "AllInclusive": "all_inclusive"}.get(
                            str(meal_raw.get("code") or ""))
                cancel_raw = rate.get("cancellation") or {}
                cancel, cancel_at = cancellation(cancel_raw, capture.platform, total,
                                                  capture.checked_at)
                taxes = rate.get("taxes") or {}
                tax_items = taxes.get("items")
                fees = fee_text(tax_items) if tax_items else ""
                method = rate.get("payment_method")
                conditional = "Оплата частями" if method == "buy_now_pay_later" else None
                if method not in {"credit_card", "sbp", "buy_now_pay_later", "at_hotel",
                                  "front_desk", "layaway"}:
                    conditional = f"Способ оплаты: {method or 'не раскрыт'}"
                timing = {"at_hotel": "at_hotel", "front_desk": "at_hotel",
                          "credit_card": "now", "layaway": "later"}.get(method)
                if conditional == "Оплата частями":
                    timing = "later"
                name = room.get("name") or "Категория номера не раскрыта"
                fragments = {
                    "public_total": dump(total_data), "meal_plan": meal_raw.get("name", ""),
                    "raw_rate": "\n".join([name, meal_raw.get("name", ""), dump(cancel_raw),
                                              f"{total} ₽ за весь период", str(method)]),
                    "cancellation_type": dump(cancel_raw), "payment_timing": str(method),
                    "scenario_validation": dump(result["booking_params"]),
                    "additional_fees": fees,
                }
                offers.append(offer(
                    capture, hotel, observation_id, f"{ri}-{pi}", room=name, total=total,
                    meal=meal, cancel=cancel, cancel_at=cancel_at, timing=timing,
                    bed_type=bed(str(rate.get("bed_type", ""))), fragments=fragments,
                    taxes=True if tax_items == [] else False if tax_items else None,
                    conditional=conditional, observed=observed,
                ))
    else:
        for ri, rate in enumerate(data["rates"]):
            rooms = rate.get("rooms") or []
            if rate.get("occupancy") != scenario.adults or len(rooms) != 1:
                continue
            meal_values = rate.get("meal") or []
            meal = {"nomeal": "none", "breakfast": "breakfast", "half-board": "half_board",
                    "full-board": "full_board", "all-inclusive": "all_inclusive"}.get(
                        meal_values[0]) if len(meal_values) == 1 else None
            beds = rooms[0].get("bedding_data") or []
            bed_type = beds[0] if len(beds) == 1 and beds[0] in {
                "double", "twin", "single", "king", "queen",
            } else None
            display = rate.get("display_prices") or {}
            extra = [*(display.get("taxes_not_included_now") or []),
                     *(display.get("taxes_not_included_later") or [])]
            translations = {t["key"]: t["trans"] for t in
                            (rate.get("trans") or {}).get("ru", {}).get("taxes", [])
                            if "key" in t and "trans" in t}
            fees = fee_text(extra, translations) if extra else ""
            for pi, payment in enumerate((rate.get("payment_options") or {}).get(
                "payment_types", []
            )):
                total = money(payment.get("amount"))
                if (payment.get("is_enabled") is not True or total is None
                        or payment.get("currency_code") != "RUB"):
                    continue
                cancel_raw = rate.get("cancellation_info") or {}
                cancel, cancel_at = cancellation(cancel_raw, capture.platform, total,
                                                  capture.checked_at)
                name = rate.get("room_name") or rooms[0].get("room_name") or "Номер"
                timing = {"now": "now", "hotel": "at_hotel", "later": "later"}.get(
                    payment.get("type"))
                fragments = {
                    "public_total": str(total), "meal_plan": dump(meal_values),
                    "cancellation_type": dump(cancel_raw),
                    "payment_timing": str(payment.get("type")),
                    "raw_rate": "\n".join([name, dump(meal_values), dump(cancel_raw),
                                              f"{total} ₽ за весь период"]),
                    "additional_fees": fees,
                    "scenario_validation": "Accepted dated HTTP request; hotel ID and occupancy "
                    "match. Response does not echo the dates.",
                    "scenario_binding": "api_request_response",
                }
                offers.append(offer(
                    capture, hotel, observation_id, f"{ri}-{pi}", room=name, total=total,
                    meal=meal, cancel=cancel, cancel_at=cancel_at, timing=timing,
                    bed_type=bed_type, fragments=fragments,
                    taxes=False if extra else True if "taxes_not_included_now" in display
                    and "taxes_not_included_later" in display else None,
                ))
    return offers
