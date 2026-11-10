import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from rate_shopper.domain.capture import BrowserCapture, HotelTarget
from rate_shopper.domain.models import HotelRegistration, Offer, Platform, Scenario, Status

MONETARY = re.compile(r"(?<![\d.,])(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*₽")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u200b", "")).strip()


def money(text: str | None) -> list[Decimal]:
    if not text:
        return []
    return [Decimal(re.sub(r"\s", "", m).replace(",", ".")) for m in MONETARY.findall(text)]


def category(name: str) -> str:
    # Exact normalized names only: no fuzzy collapsing studio/twin/view/accessible variants.
    return clean(name).casefold().replace("ё", "е")


def room_name(text: str) -> str:
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    # Availability badges can precede the actual heading in Otello cards.
    while lines and re.fullmatch(r"(?:Доступно|Осталось)\s+\d+\s+номер[аов]*", lines[0]):
        lines.pop(0)
    return lines[0] if lines else ""


def bed(text: str) -> str | None:
    lines = [clean(line).casefold() for line in text.splitlines()]
    if "тип кровати может измениться" in lines:
        return "allocation_not_guaranteed"
    for label, value in [("king", "king"), ("queen", "queen")]:
        if f"кровать размера «{label} size»" in lines:
            return value
    for line in lines:
        if len(line) > 110:
            continue
        if "или" in line and "кроват" in line:
            return "allocation_not_guaranteed"
        if line in {"две односпальные кровати", "2 односпальные кровати"}:
            return "twin"
        if line in {"двуспальная кровать", "1 двуспальная кровать"}:
            return "double"
        if "кровать размера «queen size»" == line:
            return "queen"
        if "кровать размера «king size»" == line:
            return "king"
        if line == "диван-кровать":
            return "sofa"
    return None


def source_scenario(capture: BrowserCapture, requested: Scenario) -> Scenario | None:
    query = parse_qs(urlsplit(capture.url).query)
    try:
        if capture.platform == Platform.OTELLO:
            groups = json.loads(query["guest_groups"][0])
            if len(groups) != 1:
                return None
            adults = groups[0]["adults"]
            children = groups[0].get("children", [])
            checkin, checkout = query["checkin"][0], query["checkout"][0]
            # Visible form must independently confirm occupancy and whole-stay duration.
            visible = clean(capture.snapshot)
            if f"{requested.nights} ноч" not in visible or "1 номер" not in visible:
                return None
            if f"{adults} взрослых" not in visible:
                return None
        elif capture.platform == Platform.OZON:
            adults = int(query["Dlts"][0])
            children = []
            if any(k.casefold().startswith("child") for k in query):
                return None
            checkin, checkout = query["checkIn"][0], query["checkOut"][0]
            visible = clean(capture.snapshot)
            if f"{requested.nights} ноч" not in visible or f"{adults} гост" not in visible:
                return None
        elif capture.platform == Platform.YANDEX:
            checkin, checkout = query["checkinDate"][0], query["checkoutDate"][0]
            adults, children = int(query["adults"][0]), []
            visible = clean(capture.snapshot)
            # Sold-out cards have no tariff duration. Accept an explicit visible date pair.
            months = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен",
                      "окт", "ноя", "дек")
            start, end = datetime.fromisoformat(checkin), datetime.fromisoformat(checkout)
            date_pair = re.search(
                rf"\b{start.day} {months[start.month - 1]}[а-я]*\s*[—–-]\s*"
                rf"{end.day} {months[end.month - 1]}[а-я]*\b", visible.casefold()
            )
            if (f"{requested.nights} ноч" not in visible and not date_pair
                    or f"{adults} взрослых" not in visible):
                return None
            if query.get("rooms", ["1"]) != ["1"]:
                return None
            if any(k.lower().startswith(("child", "ages")) for k in query):
                return None
        elif capture.platform == Platform.OSTROVOK:
            dates = query["dates"][0].split("-")
            checkin, checkout = (datetime.strptime(d, "%d.%m.%Y").date().isoformat() for d in dates)
            # A single integer means one room, adults only. Reject multi-room/child notation.
            if not query["guests"][0].isdigit():
                return None
            adults, children = int(query["guests"][0]), []
            visible = clean(capture.snapshot)
            if f"На {requested.nights} ночи, для {adults} взрослых" not in visible:
                return None
        else:
            return None
        data = requested.model_dump()
        data.update(
            checkin=checkin, checkout=checkout, adults=adults, children_ages=children, rooms=1
        )
        actual = Scenario.model_validate(data)
        return actual
    except (KeyError, TypeError, ValueError):
        return None


def hotel_verified(capture: BrowserCapture, target: HotelTarget) -> bool:
    path = urlsplit(capture.url).path.rstrip("/")
    expected = target.urls.get(capture.platform)
    if (
        not expected
        or path != urlsplit(expected).path.rstrip("/")
        or urlsplit(capture.url).hostname != urlsplit(expected).hostname
    ):
        return False
    title = clean(capture.title).casefold()
    scope = capture.title if target.country == "Россия" else capture.title + capture.snapshot
    geo = target.geo.casefold()
    geo_aliases = {
        "москва": ("москва", "москве"),
        "санкт-петербург": ("санкт-петербург", "санкт-петербурге"),
    }.get(geo, (geo,))
    if not any(
        g in clean(scope).casefold()
        for g in (*geo_aliases, *(a.casefold() for a in target.location_aliases))
    ):
        return False
    if not any(alias.casefold() in title for alias in target.aliases):
        return False
    return all(
        token.casefold() in clean(capture.snapshot).casefold() for token in target.address_tokens
    )


def capture_status(capture: BrowserCapture, requested: Scenario, target: HotelTarget) -> Status:
    text = clean(capture.snapshot)
    if "captcha" in capture.url.casefold() or capture.title in {"Вы не робот?", "Ой!"}:
        return Status.CAPTCHA
    if capture.collection_error == "RATE_LIMITED":
        return Status.RATE_LIMITED
    if capture.collection_error:
        return Status.CONNECTOR_ERROR
    if not hotel_verified(capture, target):
        return Status.UNKNOWN
    observed = source_scenario(capture, requested)
    if observed is None or observed.signature() != requested.signature():
        return Status.SCENARIO_MISMATCH
    if any(label in text for label in (
        "Номера закончились", "Нет номеров на ваши даты",
        "Нет доступных вариантов на ваши даты",
        "Не нашлось предложений на ваши даты",
    )):
        return Status.SOLD_OUT
    if any(room.rates for room in capture.cards):
        return Status.AVAILABLE
    return Status.PRICE_NOT_EXPOSED


def extract(
    capture: BrowserCapture, requested: Scenario, target: HotelTarget, observation_id: str
) -> list[Offer]:
    status = capture_status(capture, requested, target)
    if status != Status.AVAILABLE:
        return []
    actual = source_scenario(capture, requested)
    registration = None
    # Only an explicit registration label in rendered source content is evidence.
    reg = re.search(
        r"(?:реестровый номер|реестровая запись|номер реестровой записи|"
        r"регистрационный номер|номер в реестре|рег\.\s*номер|объект\s*№)"
        r"[\s\S]{0,100}?([СC]\d{12})",
        capture.snapshot,
        re.I,
    )
    if reg and target.country == "Россия":
        registration = HotelRegistration(
            registry="ru_accommodation",
            country="RU",
            registration_id=reg.group(1),
            source_url=capture.url,
            source_text=reg.group(0),
            verification_status="source_observed",
            checked_at=capture.checked_at,
        )
    offers: list[Offer] = []
    for card_i, room in enumerate(capture.cards):
        name = room_name(room.text)
        if not name:
            continue
        area = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:м[²2]|кв\.м)", clean(room.text))
        for rate_i, rate in enumerate(room.rates):
            text = clean(rate.text)
            # A separately payable fee is not a crossed-out reference price.
            # Keep foreign-currency charges verbatim; never invent an FX rate.
            fee_match = re.search(r"\+\s*([^\n]*?(?:налоги и сборы|сборы и налоги))",
                                  rate.price or "", re.I)
            fee_text = clean(fee_match.group(0)) if fee_match else ""
            base_price = (rate.price or "")[:fee_match.start()] if fee_match else rate.price
            price_values = money(base_price)
            rub_fees = money(fee_text)
            # No fallback scanning the full document for prices.
            if not price_values or len(price_values) > 2 or price_values[0] <= 0:
                continue
            public: Decimal | None = price_values[0]
            bank = member = mobile = None
            access = "public"
            if re.search(r"ozon\s*(?:карт|банк)|с картой|Яндекс Пэй", text, re.I):
                bank, public, access = public, None, "bank"
            elif re.search(r"в приложении|мобильн", text, re.I):
                mobile, public, access = public, None, "mobile"
            elif re.search(r"войдите|авториз|с плюсом|для участников", text, re.I):
                member, public, access = public, None, "member"
            elif re.search(r"корпоративн", text, re.I):
                member, public, access = public, None, "corporate"
            elif capture.authorization_state == "authenticated":
                # A logged-in session does not establish the anonymous public price.
                member, public, access = public, None, "personal"
            meal_raw = clean(rate.meal or rate.text)
            meal_lower = meal_raw.casefold()
            meal = (
                "none"
                if "без питания" in meal_lower
                or "питание не включено" in meal_lower
                else "all_inclusive"
                if "всё включено" in meal_lower or "все включено" in meal_lower
                else "full_board"
                if "завтрак, обед и ужин" in meal_lower or "полный пансион" in meal_lower
                else "half_board"
                if "завтрак и ужин" in meal_lower or "полупансион" in meal_lower
                else "breakfast"
                if "завтрак" in meal_lower
                else None
            )
            cancellation = (
                "non_refundable"
                if "не возвращается" in text
                else "free"
                if "Бесплатная отмена" in text
                else None
            )
            fragments = {
                "room_category_normalized": name,
                "public_total": rate.price or "",
                "meal_plan": meal_raw,
                "cancellation_type": rate.cancellation or text,
                "payment_timing": rate.payment_selected or text,
                "taxes_included": fee_text or (
                    "Все налоги включены" if "Все налоги включены" in text else ""
                ),
                "additional_fees": fee_text,
                "bed_type": room.text,
                "observed_scenario": clean(capture.snapshot[:1500]),
                "hotel_canonical_id": capture.title,
                "availability_status": "Rendered tariff with price and choose control",
                "authorization_required": (
                    capture.authorization_state
                    if capture.authorization_state != "unknown"
                    else "Войти"
                    if "Войти" in capture.snapshot
                    else ""
                ),
                "access_type": text,
                "price_basis": text,
                "raw_rate": rate.text,
                "raw_room": room.text,
                "pointer": f"/cards/{card_i}/rates/{rate_i}",
            }
            for supplement in capture.supplements:
                if supplement.card == card_i and supplement.rate == rate_i:
                    fragments[f"{supplement.kind}_details"] = supplement.text
            # Partial date labels never become invented midnight deadlines.
            payment = (
                "now"
                if ("Оплата сейчас" in text or "Сейчас" in text) and "Отложенный платёж" not in text
                else None
            )
            if capture.platform == Platform.OSTROVOK and "Отложенная оплата" in text:
                payment = "later"
            if capture.platform == Platform.OTELLO and rate.payment_selected:
                payment = {
                    "Сейчас": "now", "Оплата сейчас": "now",
                    "Отложенный платёж": "later", "В отеле": "at_hotel",
                }.get(clean(rate.payment_selected))
            identity = hashlib.sha256(f"{observation_id}/{card_i}/{rate_i}".encode()).hexdigest()[
                :20
            ]
            offer = Offer.model_validate(
                dict(
                    id=identity,
                    observation_id=observation_id,
                    platform=capture.platform,
                    scenario_id=requested.id,
                    hotel_canonical_id=target.id,
                    hotel_source_id=urlsplit(capture.url).path.rstrip("/").split("/")[-1],
                    hotel_name_raw=capture.title,
                    room_name_raw=name,
                    registration=registration,
                    room_category_normalized=category(name),
                    bed_type=bed(rate.text + "\n" + room.text),
                    room_area_m2=area.group(1).replace(",", ".") if area else None,
                    meal_plan=meal,
                    cancellation_type=cancellation,
                    payment_timing=payment,
                    public_total=public,
                    bank_product_total=bank,
                    member_total=member,
                    mobile_total=mobile,
                    crossed_out_total=price_values[1] if len(price_values) > 1 else None,
                    taxes_included=False if fee_text else (
                        True if "Все налоги включены" in text else None
                    ),
                    taxes_total=rub_fees[0] if len(rub_fees) == 1 else None,
                    currency="RUB",
                    availability_status=Status.AVAILABLE,
                    authorization_required=(
                        True
                        if capture.authorization_state == "authenticated"
                        else False
                        if capture.authorization_state == "anonymous"
                        or 'button "Войти"' in capture.snapshot
                        else None
                    ),
                    source_url=capture.url,
                    source_fragments=fragments,
                    extraction_confidence="0.95",
                    price_basis="stay_total",
                    access_type=access,
                    observed_scenario=actual,
                    url_scenario=actual,
                )
            )
            offers.append(offer)
    return offers
