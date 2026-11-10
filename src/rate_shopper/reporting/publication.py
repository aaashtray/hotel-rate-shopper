"""Build a public-only, allowlisted report without publishing session evidence."""

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rate_shopper.reporting.html import write_html

PUBLIC_NOTE = (
    "Публичный срез. Личные, корпоративные и банковские цены не опубликованы. "
    "Это сохранённые наблюдения, а не цены в реальном времени."
)
URL_KEYS = {
    "checkin", "checkout", "checkIn", "checkOut", "check_in", "check_out",
    "guest_groups", "guests", "adults", "children", "rooms", "dates",
    "currency", "cityOrRegionId", "hotelId", "Dlts",
}
HOSTS = {"otello.ru", "www.ozon.ru", "ozon.ru", "ostrovok.ru", "travel.yandex.ru"}


def public_url(value: str | None) -> str:
    if not value:
        return ""
    u = urlsplit(value)
    if u.scheme != "https" or u.hostname not in HOSTS or u.username or u.password:
        return ""
    query = urlencode([(k, v) for k, v in parse_qsl(u.query) if k in URL_KEYS])
    return urlunsplit(("https", u.hostname, u.path, query, ""))


def public_report(source: dict[str, Any]) -> dict[str, Any]:
    """Prices remain unchanged; do not carry arbitrary source fields into public JSON."""
    result = {k: deepcopy(source[k]) for k in (
        "schema_version", "platforms", "provenance", "checked_at", "scenario", "statistics",
    )}
    result["publication"] = {"public_only": True, "note": PUBLIC_NOTE}
    result["hotels"] = [
        {k: deepcopy(h[k]) for k in ("id", "name", "country", "geo", "stars")}
        for h in source["hotels"]
    ]
    fields = (
        "id", "platform", "scenario_id", "hotel_canonical_id", "room_name_raw",
        "room_category_normalized", "bed_type", "room_area_m2", "meal_plan",
        "cancellation_type", "cancellation_deadline", "payment_timing", "public_total",
        "taxes_total", "taxes_included", "currency", "availability_status",
        "authorization_required", "access_type", "price_basis",
    )
    offers = []
    for o in source["offers"]:
        if o["access_type"] != "public" or o["authorization_required"] is not False:
            continue
        if o["public_total"] is None:
            continue
        item = {k: deepcopy(o.get(k)) for k in fields}
        item["source_url"] = public_url(o["source_url"])
        # Room descriptions can contain neighbouring prices. Publish only individual
        # public tariff conditions, never a full room/page snapshot or session text.
        fragments = {k: str(o["source_fragments"].get(k, "")) for k in (
            "meal_plan", "cancellation_type", "payment_timing", "additional_fees",
        )}
        fragments["raw_rate"] = "\n".join([o["room_name_raw"], *fragments.values()])
        item["source_fragments"] = fragments
        offers.append(item)
    result["offers"] = offers
    ids = {o["id"] for o in offers}
    counts = Counter((o["hotel_canonical_id"], o["platform"]) for o in offers)
    result["observations"] = []
    for o in source["observations"]:
        item = {k: deepcopy(o.get(k)) for k in (
            "hotel_id", "hotel", "platform", "status", "checked_at", "mapping_note",
        )}
        item["source_url"] = public_url(o.get("source_url"))
        item["offer_count"] = counts[(o["hotel_id"], o["platform"])]
        item["reason"] = ""
        if o["status"] == "AVAILABLE" and item["offer_count"] == 0:
            item["status"] = "WITHHELD"
            item["reason"] = "Получены только непубличные цены; в открытый отчёт не включены."
        result["observations"].append(item)
    result["matches"] = [deepcopy(m) for m in source["matches"]
                         if m["reference_offer_id"] in ids and m["competitor_offer_id"] in ids]
    result["quality_issues"] = {k: v for k, v in source["quality_issues"].items() if k in ids}
    statuses = Counter(o["status"] for o in result["observations"])
    result["metrics"] = dict(
        expected_observations=len(result["observations"]),
        captured_observations=sum(bool(o["checked_at"]) for o in result["observations"]),
        extracted_offers=len(offers), available=statuses["AVAILABLE"],
        sold_out=statuses["SOLD_OUT"],
        unresolved=len(result["observations"]) - statuses["AVAILABLE"] - statuses["SOLD_OUT"],
        comparable_pairs=sum(m["percent_gap"] is not None for m in result["matches"]),
        review_pairs=sum(m["manual_review_required"] for m in result["matches"]),
    )
    # A future report must not accidentally retain a private reference in a statistic.
    for row in result["statistics"]["rows"] + result["statistics"]["verified_rows"]:
        for key in ("reference_offer_id", "competitor_offer_id"):
            if row[key] is not None and row[key] not in ids:
                raise ValueError("Statistics reference a non-public offer")
    result.update(status="PARTIAL_SUCCESS", collection_status="PARTIAL_SUCCESS",
                  notes=[PUBLIC_NOTE], rejected_captures=[], excluded_platforms={})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare public-only static report")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = public_report(json.loads(args.source.read_text()))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False) + "\n")
    write_html(report, args.output)
    (args.output / ".nojekyll").touch()
    print(f"Published projection: {len(report['offers'])} public offers")


if __name__ == "__main__":
    main()
