from html.parser import HTMLParser
from urllib.parse import urlsplit

from rate_shopper.domain.models import RawObservation, Status


class TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.parts.append(data)


def page_title(body: bytes) -> str:
    parser = TitleParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return "".join(parser.parts).strip()


def classify(observation: RawObservation, title: str) -> tuple[Status, str]:
    parts = urlsplit(observation.final_url or "")
    if observation.http_status == 429:
        return Status.RATE_LIMITED, "HTTP 429; no retry"
    if observation.error_code in {"TRANSPORT_ERROR", "RESPONSE_TOO_LARGE"}:
        return Status.CONNECTOR_ERROR, observation.error_code
    if parts.path == "/showcaptcha" or title in {"Вы не робот?", "Ой!"}:
        return Status.CAPTCHA, "Yandex challenge URL or challenge page title"
    if observation.http_status == 401 or parts.hostname in {"passport.yandex.ru", "id.yandex.ru"}:
        return Status.AUTH_REQUIRED, "Authentication required; no login attempted"
    if observation.http_status is None or observation.http_status >= 400:
        return Status.CONNECTOR_ERROR, f"HTTP {observation.http_status}; not proof of sold-out"
    if observation.error_code:
        return Status.CONNECTOR_ERROR, observation.error_code
    return Status.PARSE_ERROR, "No verified tariff schema; no prices extracted"
