"""Immutable HTTP evidence; kept private, independently replayable."""

from datetime import datetime
from typing import Any, Literal

from rate_shopper.domain.models import Model, Platform, Scenario


class ApiCapture(Model):
    provenance: Literal["observed", "synthetic"]
    platform: Platform
    hotel_id: str
    checked_at: datetime
    url: str
    requested_url: str
    title: str
    endpoint: str
    request_parameters: dict[str, Any]
    scenario: Scenario
    response_text: str
    http_status: int | None = None
    collection_error: str | None = None
    capture_method: Literal["http_json"] = "http_json"
    coverage: Literal["expanded"] = "expanded"
    authorization_state: Literal["anonymous"] = "anonymous"
