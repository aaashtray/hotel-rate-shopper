"""Opt-in local collector. No profiles, credentials, stealth or challenge solving."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rate_shopper.connectors import ostrovok
from rate_shopper.domain.capture import BatchConfig, BrowserCapture
from rate_shopper.domain.models import Platform, Scenario

DOM_CARDS = """({room, rate, price, meal, cancellation, payment}) =>
Array.from(document.querySelectorAll(room)).map(e => ({
 text:e.innerText, rates:Array.from(e.querySelectorAll(rate)).map(r=>({
 text:r.innerText, price:r.querySelector(price)?.innerText || null,
 meal:meal ? r.querySelector(meal)?.innerText || null : null,
 cancellation:cancellation ? r.querySelector(cancellation)?.innerText || null : null,
 payment_selected:payment ? r.querySelector(payment)?.innerText || null : null
 }))}))"""
SELECTORS: dict[Platform, dict[str, str | None]] = {
    Platform.OSTROVOK: {"room": ostrovok.ROOM_SELECTOR,
                        "price": '[class*="Rates_cell_price__"]'},
    Platform.OTELLO: {
        "room": '[data-n="wat-room-minicard"]',
        "rate": '[data-n="wat-rate-plan"]',
        "price": '[data-n="wat-offer-price"]',
        "meal": '[data-n="wat-room-offer-meal-type"]',
        "cancellation": '[data-n="wat-room-offer-cancellation"]',
        "payment": '[data-n="wat-room-offer-payment"][data-s="checked"]',
    },
    Platform.OZON: {
        "room": ".travel_ub1_2",
        "rate": ".travel_bv_2",
        "price": ".travel_v1b_2",
        "meal": None,
        "cancellation": None,
    },
}


def scenario_url(url: str, platform: Platform, scenario: Scenario) -> str:
    if scenario.children_ages or scenario.rooms != 1:
        raise ValueError("Browser collector currently supports one room and no children")
    parts = urlsplit(url)
    hosts = {
        Platform.OTELLO: {"otello.ru"},
        Platform.OZON: {"www.ozon.ru", "ozon.ru"},
        Platform.OSTROVOK: {"ostrovok.ru"},
        Platform.YANDEX: {"travel.yandex.ru"},
    }
    if parts.scheme != "https" or parts.hostname not in hosts.get(platform, set()):
        raise ValueError("Unexpected source URL")
    query = dict(parse_qsl(parts.query))
    if platform == Platform.OTELLO:
        query.update(
            checkin=str(scenario.checkin),
            checkout=str(scenario.checkout),
            guest_groups=json.dumps([{"adults": scenario.adults}]),
        )
    elif platform == Platform.OZON:
        query.update(
            checkIn=str(scenario.checkin),
            checkOut=str(scenario.checkout),
            Dlts=str(scenario.adults),
        )
    elif platform == Platform.OSTROVOK:
        query = {
            "search": "yes",
            "dates": (f"{scenario.checkin:%d.%m.%Y}-{scenario.checkout:%d.%m.%Y}"),
            "guests": str(scenario.adults),
        }
    else:
        query = {
            "checkinDate": str(scenario.checkin),
            "checkoutDate": str(scenario.checkout),
            "adults": str(scenario.adults),
        }
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


async def collect(
    config: BatchConfig, scenario: Scenario, output: Path, headless: bool = False
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    output.mkdir(parents=True, exist_ok=True)
    stopped: set[Platform] = set()
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(locale="ru-RU")
        page = await context.new_page()
        for hotel in config.hotels:
            for platform in config.platforms:
                if platform in stopped or platform not in SELECTORS or platform not in hotel.urls:
                    continue
                url = scenario_url(hotel.urls[platform], platform, scenario)
                error = None
                cards = []
                snapshot = ""
                title = ""
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    if response and response.status == 429:
                        stopped.add(platform)
                        error = "RATE_LIMITED"
                    else:
                        await page.wait_for_function(
                            "s => Array.from(document.querySelectorAll(s))"
                            ".some(e => /[0-9][\\s\\S]*₽/.test(e.innerText)) || "
                            "/Нет номеров на ваши даты|Нет доступных вариантов на ваши даты|"
                            "Номера закончились|Вы не робот|captcha/i.test("
                            "document.body.innerText)",
                            arg=SELECTORS[platform]["price"],
                            timeout=30000,
                        )
                    title = await page.title()
                except Exception as exc:
                    error = type(exc).__name__
                try:
                    if platform == Platform.OTELLO and hotel.country == "Россия" and not error:
                        registry_button = page.get_by_role(
                            "button", name="Об объекте и исполнителе", exact=True
                        )
                        if await registry_button.count():
                            await registry_button.click()
                            await page.get_by_text("Данные о классификации объекта").wait_for(
                                state="visible", timeout=5000
                            )
                    snapshot = await page.locator("body").inner_text(timeout=5000)
                    if await page.get_by_role("button", name="Войти", exact=True).count():
                        snapshot = 'button "Войти"\n' + snapshot
                    cards = (
                        await page.evaluate(ostrovok.DOM_CARDS)
                        if platform == Platform.OSTROVOK
                        else await page.evaluate(DOM_CARDS, SELECTORS[platform])
                    )
                except Exception as exc:
                    error = error or type(exc).__name__
                if "captcha" in page.url.lower() or "Вы не робот" in title:
                    stopped.add(platform)
                    error = "CAPTCHA"
                capture = BrowserCapture(
                    provenance="observed",
                    platform=platform,
                    checked_at=datetime.now(UTC),
                    url=page.url,
                    requested_url=url,
                    title=title,
                    snapshot=snapshot,
                    cards=cards,
                    collection_error=error,
                )
                data = capture.model_dump_json(indent=2).encode()
                digest = hashlib.sha256(data).hexdigest()
                (output / f"{digest}.json").write_bytes(data)
                results.append(
                    {
                        "hotel": hotel.id,
                        "platform": platform.value,
                        "rooms": len(cards),
                        "error": error,
                    }
                )
                await asyncio.sleep(2)
        await browser.close()
    return {"results": results, "stopped_platforms": sorted(stopped)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Opt-in public browser collection")
    parser.add_argument("--hotels", type=Path, default=Path("config/hotels.json"))
    parser.add_argument("--scenario", type=Path, default=Path("config/scenario.json"))
    parser.add_argument("--output", type=Path, default=Path("data/browser"))
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    result = asyncio.run(
        collect(
            BatchConfig.model_validate_json(args.hotels.read_bytes()),
            Scenario.model_validate_json(args.scenario.read_bytes()),
            args.output,
            args.headless,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(r["error"] for r in result["results"]) else 0
