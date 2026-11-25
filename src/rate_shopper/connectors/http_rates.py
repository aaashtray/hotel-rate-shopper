"""Read-only anonymous hotel endpoints. No profiles, challenges or browser emulation."""

import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from rate_shopper.connectors.browser import scenario_url
from rate_shopper.domain.api_capture import ApiCapture
from rate_shopper.domain.capture import BatchConfig, HotelTarget
from rate_shopper.domain.models import Platform, Scenario, Status
from rate_shopper.scenarios.weekend import MOSCOW

SUPPORTED = (Platform.OTELLO, Platform.OSTROVOK)


def source_id(hotel: HotelTarget, platform: Platform) -> str:
    url = hotel.urls[platform]
    path = urlsplit(url).path
    if platform == Platform.OTELLO:
        found = re.fullmatch(r"/hotel/(\d+)/?", path)
        if not found:
            raise ValueError("Unrecognized Otello hotel URL")
        return found[1]
    parts = path.strip("/").split("/")
    if len(parts) < 5 or parts[0] != "hotel" or not re.fullmatch(r"[\w-]+", parts[-1]):
        raise ValueError("Unrecognized Ostrovok hotel URL")
    return parts[-1]


def request_spec(
    hotel: HotelTarget, platform: Platform, scenario: Scenario,
) -> tuple[str, dict[str, Any]]:
    if scenario.rooms != 1 or scenario.children_ages:
        raise ValueError("Only one room, adults without children is supported")
    # Validates origin before deriving IDs, and rejects unexpected URLs.
    scenario_url(hotel.urls[platform], platform, scenario)
    hotel_id = source_id(hotel, platform)
    if platform == Platform.OTELLO:
        return f"https://otello.api.2gis.com/api/v2/properties/{hotel_id}/offers", {
            "checkin_date": str(scenario.checkin), "checkout_date": str(scenario.checkout),
            "guest_groups": json.dumps([{"adults": scenario.adults, "children": []}]),
        }
    if platform == Platform.OSTROVOK:
        return "https://ostrovok.ru/hotel/search/v1/site/hp/search", {
            "arrival_date": str(scenario.checkin), "departure_date": str(scenario.checkout),
            "hotel": hotel_id, "currency": "RUB", "lang": "ru",
            "paxes": [{"adults": scenario.adults, "child_ages": []}],
            "search_uuid": str(uuid.uuid4()), "guru_auth_prices_enabled": False,
        }
    raise ValueError("HTTP source is not supported")


def capture(
    client: httpx.Client, hotel: HotelTarget, platform: Platform, scenario: Scenario,
    *, blocked: str | None = None,
) -> ApiCapture:
    endpoint, parameters = request_spec(hotel, platform, scenario)
    url = scenario_url(hotel.urls[platform], platform, scenario)
    raw, http_status, error = "", None, blocked
    if not blocked:
        query = {"body": json.dumps(parameters)} if platform == Platform.OSTROVOK else parameters
        for attempt in range(2):
            try:
                client.cookies.clear()
                response = client.get(endpoint, params=query)
                http_status, raw = response.status_code, response.text
                if http_status == 429:
                    error = Status.RATE_LIMITED.value
                elif http_status in {401, 403} or 300 <= http_status < 400:
                    error = Status.AUTH_REQUIRED.value
                elif "json" not in response.headers.get("content-type", ""):
                    error = (Status.CAPTCHA.value if re.search(
                        r"captcha|challenge|проверка браузера|вы не робот", raw, re.I
                    ) else Status.PARSE_ERROR.value)
                elif http_status >= 500 and attempt == 0:
                    time.sleep(2)
                    continue
                elif http_status != 200:
                    error = Status.CONNECTOR_ERROR.value
                break
            except httpx.HTTPError:
                error = Status.CONNECTOR_ERROR.value
                if attempt == 0:
                    time.sleep(2)
                    error = None
    return ApiCapture(
        provenance="observed", platform=platform, hotel_id=hotel.id,
        checked_at=datetime.now(UTC), url=url, requested_url=url, title=hotel.name,
        endpoint=endpoint, request_parameters=parameters, scenario=scenario,
        response_text=raw, http_status=http_status, collection_error=error,
    )


def collect_http(
    config: BatchConfig, scenario: Scenario, output: Path, *, interval: float = 1.0,
) -> None:
    if scenario.checkin <= datetime.now(MOSCOW).date():
        raise ValueError("Check-in must be in the future")
    output.mkdir(parents=True, exist_ok=True)
    def collect_platform(platform: Platform) -> None:
        blocked: str | None = None
        with httpx.Client(timeout=45, follow_redirects=False,
                          headers={"Accept": "application/json",
                                   "User-Agent": "HotelRateShopper/0.4"}) as client:
            for hotel in config.hotels:
                if platform not in config.platforms or platform not in hotel.urls:
                    continue
                path = output / f"{hotel.id}-{platform.value}.json"
                if path.exists():
                    raise FileExistsError(f"Immutable capture already exists: {path}")
                observation = capture(client, hotel, platform, scenario,
                                      blocked=blocked)
                with path.open("x") as stream:
                    stream.write(observation.model_dump_json(indent=2) + "\n")
                if observation.collection_error in {
                    Status.CAPTCHA, Status.RATE_LIMITED, Status.AUTH_REQUIRED,
                }:
                    blocked = observation.collection_error
                print(f"{hotel.id} {platform.value}: "
                      f"{observation.collection_error or observation.http_status}", flush=True)
                if blocked is None:
                    time.sleep(interval)
    # Independent hosts run concurrently; requests to each host remain sequential.
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(collect_platform, SUPPORTED))
