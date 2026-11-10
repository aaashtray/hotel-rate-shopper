"""Synthetic publication checks: no private prices or session evidence escape."""
import json
from copy import deepcopy
from typing import Any

import pytest

from rate_shopper.reporting.publication import public_report, public_url


def synthetic_report() -> dict[str, Any]:
    public = dict(
        id="public", platform="otello", hotel_canonical_id="hotel", access_type="public",
        authorization_required=False, public_total="100.01", room_name_raw="Synthetic room",
        source_url="https://otello.ru/hotel/test?checkin=2026-11-20&token=PRIVATE_SENTINEL",
        source_fragments={"raw_rate": "PRIVATE_SENTINEL", "bed_type": "PRIVATE_SENTINEL",
                          "meal_plan": "Без питания", "additional_fees": ""},
        member_total="PRIVATE_SENTINEL", internal_secret="PRIVATE_SENTINEL",
    )
    private = {**deepcopy(public), "id": "private", "platform": "yandex_travel",
               "access_type": "corporate", "authorization_required": True,
               "public_total": "1", "room_name_raw": "PRIVATE_SENTINEL"}
    observations = [dict(hotel_id="hotel", hotel="Synthetic", platform=p, status="AVAILABLE",
                         checked_at="2026-11-10T10:00:00Z", mapping_note="",
                         source_url=public["source_url"], evidence="PRIVATE_SENTINEL",
                         reason="PRIVATE_SENTINEL") for p in ("otello", "yandex_travel")]
    return dict(schema_version=6, platforms=["otello", "yandex_travel"],
                provenance="synthetic", checked_at="2026-11-10T10:00:00Z", scenario={},
                hotels=[dict(id="hotel", name="Synthetic", country="Test", geo="Test", stars=3,
                             private="PRIVATE_SENTINEL")], observations=observations,
                offers=[public, private], matches=[], quality_issues={"public": []},
                statistics={"rows": [], "verified_rows": []}, secret="PRIVATE_SENTINEL")


def test_publication_removes_private_content_without_mutating_source() -> None:
    source = synthetic_report()
    result = public_report(source)
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert result["offers"][0]["public_total"] == "100.01"
    assert result["metrics"]["extracted_offers"] == 1
    assert result["observations"][1]["status"] == "WITHHELD"
    assert result["observations"][1]["offer_count"] == 0
    assert len(source["offers"]) == 2
    assert source["observations"][1]["status"] == "AVAILABLE"


@pytest.mark.parametrize("access,auth", [("personal", True), ("bank", False),
                                        ("public", None), ("public", True)])
def test_publication_requires_explicit_public_access(access: str, auth: bool | None) -> None:
    source = synthetic_report()
    source["offers"][0].update(access_type=access, authorization_required=auth)
    assert public_report(source)["offers"] == []


def test_private_statistic_reference_fails_closed() -> None:
    source = synthetic_report()
    source["statistics"]["rows"] = [
        dict(reference_offer_id="public", competitor_offer_id="private")
    ]
    with pytest.raises(ValueError, match="non-public"):
        public_report(source)


def test_url_allowlist_rejects_credentials_and_unexpected_hosts() -> None:
    assert public_url("https://user:secret@otello.ru/hotel/1") == ""
    assert public_url("https://example.com/private") == ""
    assert public_url("https://ostrovok.ru/hotel/1?guests=2&session=secret#private") == (
        "https://ostrovok.ru/hotel/1?guests=2"
    )
