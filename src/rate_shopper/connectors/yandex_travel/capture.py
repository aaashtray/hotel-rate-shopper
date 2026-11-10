import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx

from rate_shopper.domain.models import HotelEntity, Platform, RawObservation, Scenario

VERSION = "yandex-public-0.1"
MAX_BYTES = 5 * 1024 * 1024
ALLOWED_QUERY = {"checkinDate", "checkoutDate", "adults", "childrenAges", "rooms"}


def safe_url(url: str) -> str:
    """Persist no challenge/session query values."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def validate_url(url: str) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "travel.yandex.ru"
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or not parts.path.startswith("/hotels/")
        or parts.fragment
    ):
        raise ValueError("Only public https://travel.yandex.ru/hotels/ URLs are allowed")
    if any(key not in ALLOWED_QUERY for key, _ in parse_qsl(parts.query)):
        raise ValueError("Unrecognized URL query key; do not send credentials or tracking data")


def save_capture(
    root: Path,
    body: bytes,
    scenario: Scenario,
    requested_url: str,
    final_url: str,
    checked_at: datetime,
    http_status: int | None,
    error_code: str | None = None,
    connector_version: str = VERSION,
    capture_method: str = "public_http",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(body).hexdigest()
    raw = root / f"{digest}.html"
    if raw.exists():
        if raw.read_bytes() != body:
            raise ValueError("Evidence integrity failure")
    else:
        with raw.open("xb") as stream:
            stream.write(body)
    capture_id = hashlib.sha256(
        (
            checked_at.isoformat()
            + requested_url
            + digest
            + scenario.model_dump_json()
            + connector_version
        ).encode()
    ).hexdigest()
    observation = RawObservation(
        id=capture_id,
        run_id=f"{connector_version}-{capture_id}",
        platform=Platform.YANDEX,
        scenario_id=scenario.id,
        requested_url=safe_url(requested_url),
        final_url=safe_url(final_url),
        checked_at=checked_at,
        http_status=http_status,
        capture_method=capture_method,
        raw_html_path=raw.name,
        auth_state="anonymous_no_cookie_jar",
        captcha_detected=False,
        connector_version=connector_version,
        content_hash=digest,
        error_code=error_code,
    )
    payload = {
        "provenance": "observed",
        "scenario": scenario.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json"),
        "requested_query": dict(parse_qsl(urlsplit(requested_url).query)),
    }
    path = root / f"{capture_id}.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text() != serialized:
        raise ValueError("Capture manifest integrity failure")
    path.write_text(serialized, encoding="utf-8")
    return path


class YandexConnector:
    """Single request; no redirect following, retries, auth or protection bypass."""

    def __init__(self, url: str, root: Path, transport: httpx.BaseTransport | None = None):
        validate_url(url)
        self.url, self.root, self.transport = url, root, transport
        self.manifest_path: Path | None = None

    def capture(self, hotel: HotelEntity, scenario: Scenario) -> RawObservation:
        # Hotel is a request target, never proof that a returned page belongs to it.
        checked_at = datetime.now(UTC)
        body = b""
        final_url = self.url
        status = None
        error = None
        try:
            with httpx.Client(
                transport=self.transport,
                follow_redirects=False,
                timeout=20,
                trust_env=False,
                headers={"User-Agent": "HotelRateShopper/0.2 public-data-research"},
            ) as client:
                with client.stream("GET", self.url) as response:
                    status = response.status_code
                    if 300 <= status < 400:
                        final_url = urljoin(self.url, response.headers.get("location", ""))
                        error = "REDIRECT_NOT_FOLLOWED"
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        if len(chunks) + len(chunk) > MAX_BYTES:
                            error = "RESPONSE_TOO_LARGE"
                            break
                        chunks.extend(chunk)
                    body = bytes(chunks)
        except httpx.HTTPError:
            error = "TRANSPORT_ERROR"
        self.manifest_path = save_capture(
            self.root, body, scenario, self.url, final_url, checked_at, status, error
        )
        return RawObservation.model_validate_json(
            json.dumps(json.loads(self.manifest_path.read_text())["observation"])
        )
