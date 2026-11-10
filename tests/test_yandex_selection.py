"""Synthetic cases for the layouts observed in Safari selection text."""

from typing import Any

import pytest

from rate_shopper.domain.capture import BrowserCapture, HotelTarget
from rate_shopper.domain.models import Scenario, Status
from rate_shopper.extraction.browser import capture_status, extract, source_scenario
from rate_shopper.extraction.yandex_selection import parse_selection

URL = "https://travel.yandex.ru/hotels/moscow/synthetic/"
TARGET = HotelTarget(
    id="synthetic",
    name="Synthetic",
    aliases=("Synthetic",),
    urls={"yandex_travel": URL},
    geo="Москва",
)
SCENARIO = Scenario(
    id="synthetic",
    created_at="2026-11-10T00:00:00Z",
    checkin="2026-11-20",
    checkout="2026-11-22",
    adults=2,
    children_ages=(),
    rooms=1,
    currency="RUB",
)
HEADER = ("private-account-sentinel\nЖильё Москвы\nSynthetic\nДаты и гости\n"
          "20 ноября\n22 ноября\n2 взрослых\nНайти\n")


def raw(body: str) -> dict[str, Any]:
    return {
        "provenance": "synthetic",
        "checked_at": "2026-11-10T21:00:00Z",
        "url": URL + "?checkinDate=2026-11-20&checkoutDate=2026-11-22&adults=2",
        "title": "Synthetic в Москве — Яндекс Путешествия",
        "text": HEADER + body,
        "authorization_state": "authenticated",
    }


def test_unlabelled_svg_price_never_becomes_public_or_assumed_pay() -> None:
    r = raw(
        "нет фото\nTwin\nБез питания\nБесплатная отмена\n100 ₽\n%\n101 ₽\n"
        "90 ₽ с\nКорпоративный\nза 2 ночи\nЗабронировать\nОб этом месте\n"
    )
    c, unresolved = parse_selection(r)
    assert len(c["cards"][0]["rates"]) == 1
    assert len(unresolved) == 1
    assert "private-account-sentinel" not in c["snapshot"]
    offers = extract(BrowserCapture.model_validate(c), SCENARIO, TARGET, "synthetic")
    assert offers[0].access_type == "corporate"
    assert offers[0].public_total is None
    r["bank_label_confirmed"] = "Яндекс Пэй"
    confirmed, unresolved = parse_selection(r)
    offers = extract(BrowserCapture.model_validate(confirmed), SCENARIO, TARGET, "synthetic")
    assert len(offers) == 2 and not unresolved
    assert offers[1].access_type == "bank"
    assert "Корпоративный" in offers[1].source_fragments["raw_rate"]


def test_two_room_suggestions_are_not_single_room_prices() -> None:
    c, _ = parse_selection(
        raw(
            "Suite\nПодробнее о предложении\nБез питания\n100 ₽\nза 2 ночи и 1 номер\n"
            "Забронировать\n2 × Single\nВ каждом из 2 номеров:\n1 кровать\n"
            "Подробнее о предложении\nБез питания\n90 ₽\nза 2 ночи и 2 номера\n"
            "Забронировать\nОб этом месте\n"
        )
    )
    assert len(c["cards"]) == 1
    assert c["cards"][0]["text"] == "Suite"
    assert c["cards"][0]["rates"][0]["price"] == "100 ₽"


def test_missing_photo_and_dinner_only_are_preserved() -> None:
    c, _ = parse_selection(
        raw("нет фото\nFamily\nВключён ужин\n100 ₽\nза 2 ночи\nЗабронировать\nОб этом месте\n")
    )
    offers = extract(BrowserCapture.model_validate(c), SCENARIO, TARGET, "synthetic")
    assert len(offers) == 1
    assert offers[0].meal_plan is None
    assert "Включён ужин" in offers[0].source_fragments["raw_rate"]


def test_sold_out_requires_actual_form_dates_not_neighbour_suggestions() -> None:
    c, _ = parse_selection(raw("Не нашлось предложений на ваши даты\nОб этом месте\n"))
    capture = BrowserCapture.model_validate(c)
    assert capture_status(capture, SCENARIO, TARGET) == Status.SOLD_OUT
    changed = capture.model_copy(
        update={"snapshot": "Цены на соседние даты 20 — 22 ноября 2 взрослых"}
    )
    assert source_scenario(changed, SCENARIO) is None
    wrong = capture.model_copy(
        update={"snapshot": capture.snapshot.replace("20 ноября", "21 ноября")}
    )
    assert source_scenario(wrong, SCENARIO) is None


def test_404_is_distinct_and_removes_profile_header() -> None:
    r = raw("")
    r.update(title="Страница не найдена", text="private-account-sentinel\nОшибка 404")
    c, _ = parse_selection(r)
    assert c["snapshot"] == "Страница не найдена"
    assert (
        capture_status(BrowserCapture.model_validate(c), SCENARIO, TARGET) == Status.HOTEL_NOT_FOUND
    )


def test_ambiguous_second_price_is_rejected() -> None:
    with pytest.raises(ValueError, match="crossed-out"):
        parse_selection(
            raw(
                "нет фото\nTwin\nБез питания\n100 ₽\n200 ₽\nза 2 ночи\n"
                "Забронировать\nОб этом месте\n"
            )
        )
