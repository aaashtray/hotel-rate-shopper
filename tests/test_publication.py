"""Synthetic publication checks: no private prices or session evidence escape."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from rate_shopper.reporting.html import write_html
from rate_shopper.reporting.publication import public_report, public_url
from rate_shopper.reporting.update import prepare_update


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
    assert public_url(
        "https://travel.yandex.ru/hotels/test/?checkinDate=2026-11-20"
        "&checkoutDate=2026-11-22&adults=2&rooms=1&session=secret"
    ) == ("https://travel.yandex.ru/hotels/test/?checkinDate=2026-11-20"
          "&checkoutDate=2026-11-22&adults=2&rooms=1")


def test_explicit_all_prices_keeps_access_and_money_without_session_evidence() -> None:
    source = synthetic_report()
    source["offers"][0]["member_total"] = None
    source["offers"][1].update(room_name_raw="Synthetic corporate room", public_total=None,
                               member_total="85.50", crossed_out_total="100.01")
    result = public_report(source, include_conditional=True)
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert len(result["offers"]) == 2
    assert result["offers"][1]["member_total"] == "85.50"
    assert result["offers"][1]["public_total"] is None
    assert result["offers"][1]["access_type"] == "corporate"
    assert result["observations"][1]["status"] == "AVAILABLE"
    assert result["observations"][1]["offer_count"] == 1
    assert result["publication"]["scope"] == "all_collected_prices"


def test_all_prices_mode_still_rejects_conditional_public_baseline() -> None:
    source = synthetic_report()
    source["statistics"]["rows"] = [
        dict(reference_offer_id="public", competitor_offer_id="private")
    ]
    with pytest.raises(ValueError, match="non-public"):
        public_report(source, include_conditional=True)


def test_public_mode_requires_a_public_total() -> None:
    source = synthetic_report()
    source["offers"][0].update(public_total=None, member_total="50")
    assert public_report(source)["offers"] == []


def test_conditional_statistics_are_separate_and_removed_from_public_only_export() -> None:
    source = synthetic_report()
    source["offers"][0]["member_total"] = None
    source["offers"][1].update(room_name_raw="Synthetic corporate room", public_total=None,
                               member_total="85.50")
    source["statistics"].update(default_scope="all", scopes={
        "all": {"rows": [dict(reference_offer_id="public", competitor_offer_id="private")]},
        "public": {"rows": []},
    })
    all_prices = public_report(source, include_conditional=True)
    assert all_prices["statistics"]["scopes"]["all"]["rows"][0]["competitor_offer_id"] == "private"
    assert "PRIVATE_SENTINEL" not in json.dumps(all_prices)
    public = public_report(source)
    assert set(public["statistics"]["scopes"]) == {"public"}
    assert public["statistics"]["default_scope"] == "public"
    assert "PRIVATE_SENTINEL" not in json.dumps(public)


def test_regular_statistics_reject_corporate_references() -> None:
    source = synthetic_report()
    source["statistics"]["scopes"] = {
        "regular": {"rows": [dict(reference_offer_id="public", competitor_offer_id="private")]}
    }
    with pytest.raises(ValueError, match="ineligible offer for regular"):
        public_report(source, include_conditional=True)


def update_fixture(source: Path, snapshot_id: str = "synthetic-new") -> None:
    source.mkdir(exist_ok=True)
    report = synthetic_report()
    report["offers"] = report["offers"][:1]
    report["offers"][0]["member_total"] = None
    report["collection_status"] = "PARTIAL_SUCCESS"
    report["monitoring"] = {"snapshot_id": snapshot_id, "private": "PRIVATE_SENTINEL"}
    (source / "report.json").write_text(json.dumps(report))
    # Explicitly synthetic workbook bytes: these tests exercise pairing, not XLSX rendering.
    (source / "hotel-rates.xlsx").write_bytes(b"synthetic workbook")
    (source / "workbook-manifest.json").write_text(json.dumps({
        key: hashlib.sha256((source / filename).read_bytes()).hexdigest()
        for filename, key in (("report.json", "report_sha256"),
                              ("hotel-rates.xlsx", "xlsx_sha256"))
    }))


def test_update_archives_previous_and_is_idempotent(tmp_path: Path) -> None:
    source, site = tmp_path / "source", tmp_path / "site"
    update_fixture(source, "synthetic-old")
    prepare_update(source, site)
    old_bytes = (site / "report.json").read_bytes()
    update_fixture(source)
    prepare_update(source, site)
    assert (site / "history/synthetic-old/report.json").read_bytes() == old_bytes
    for name in ("index.html", "hotel-interface-otello.html", "hotel-statistics-otello.html",
                 "hotel-map-otello.html"):
        archived = (site / "history/synthetic-old" / name).read_text()
        assert f'href="../../{name}"' in archived
        assert archived.count('id="current-snapshot"') == 1
        assert "Актуальный срез" in archived
        assert 'id="current-snapshot"' not in (site / name).read_text()
    current = (site / "report.json").read_bytes()
    assert b"PRIVATE_SENTINEL" not in current
    assert b"history/synthetic-old/hotel-interface-otello.html" in current
    prepare_update(source, site)
    assert (site / "report.json").read_bytes() == current


@pytest.mark.parametrize("failure", ["failed", "mismatched_excel"])
def test_invalid_update_preserves_published_version(tmp_path: Path, failure: str) -> None:
    source, site = tmp_path / "source", tmp_path / "site"
    update_fixture(source)
    prepare_update(source, site)
    previous = (site / "report.json").read_bytes()
    if failure == "failed":
        report = json.loads((source / "report.json").read_text())
        report["collection_status"] = "FAILED"
        (source / "report.json").write_text(json.dumps(report))
    else:
        (source / "hotel-rates.xlsx").write_bytes(b"stale workbook")
    with pytest.raises(ValueError):
        prepare_update(source, site)
    assert (site / "report.json").read_bytes() == previous


def test_monitoring_pages_show_actual_partial_browser_coverage(tmp_path: Path) -> None:
    report = synthetic_report()
    report["monitoring"] = {"timezone": "Europe/Moscow"}
    report["observations"].append({
        "hotel_id": "uncollected", "platform": "yandex_travel", "status": "UNKNOWN",
        "checked_at": None,
    })
    write_html(report, tmp_path)
    for name in ("index.html", "hotel-statistics-otello.html", "hotel-map-otello.html"):
        html = (tmp_path / name).read_text()
        assert "Яндекс — 1/2 (с ценами: 1)" in html
        assert "ожидают обновления" not in html
