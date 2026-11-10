"""Exploratory minima, explicitly separate from verified tariff matching.

User authorized this mode on 2026-11-10. Positive gap means Otello costs more.
Price scopes are explicit. Known extra fees and disputed identities block the gap.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from rate_shopper.domain.capture import BatchConfig
from rate_shopper.domain.models import Offer, Platform

PRICE_SCOPES = {
    "all": "Все собранные цены",
    "regular": "Без Пэй и корпоративных",
    "public": "Только публичные",
}


def statistic_price(offer: Offer, scope: str) -> Decimal | None:
    """Select only the observed price field for the declared access type."""
    if scope not in PRICE_SCOPES:
        raise ValueError(f"Unknown price scope: {scope}")
    if offer.currency != "RUB" or offer.price_basis != "stay_total":
        return None
    if scope == "public" and (
        offer.access_type != "public" or offer.authorization_required is not False
    ):
        return None
    if scope == "regular" and offer.access_type in {"bank", "corporate"}:
        return None
    field = {
        "public": offer.public_total, "personal": offer.member_total,
        "corporate": offer.member_total, "member": offer.member_total,
        "bank": offer.bank_product_total, "mobile": offer.mobile_total,
    }.get(offer.access_type or "")
    return field if field is not None and field > 0 else None


def preliminary_statistics(
    offers: list[Offer], config: BatchConfig, observations: list[dict[str, Any]],
    *, price_scope: str = "public",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    obs = {(o["hotel_id"], o["platform"]): o for o in observations}
    for hotel in config.hotels:
        cheapest: dict[Platform, Offer] = {}
        for platform in config.platforms:
            pool = [o for o in offers if o.hotel_canonical_id == hotel.id
                    and o.platform == platform and statistic_price(o, price_scope) is not None]
            if pool:
                cheapest[platform] = min(pool, key=lambda o: (
                    statistic_price(o, price_scope) or Decimal(0), o.id
                ))
        a = cheapest.get(Platform.OTELLO)
        for platform in config.platforms:
            if platform == Platform.OTELLO:
                continue
            b = cheapest.get(platform)
            a_total = statistic_price(a, price_scope) if a else None
            b_total = statistic_price(b, price_scope) if b else None
            row: dict[str, Any] = {
                "hotel_id": hotel.id, "platform": platform.value,
                "reference_offer_id": a.id if a else None,
                "competitor_offer_id": b.id if b else None,
                "reference_total": str(a_total) if a_total is not None else None,
                "competitor_total": str(b_total) if b_total is not None else None,
                "reference_access": a.access_type if a else None,
                "competitor_access": b.access_type if b else None,
                "price_scope": price_scope,
                "absolute_gap": None, "percent_gap": None, "outcome": "excluded",
                "reason": "", "identity": "unconfirmed",
            }
            if not a or not b:
                missing = Platform.OTELLO if not a else platform
                status = obs.get((hotel.id, missing), {}).get("status", "UNKNOWN")
                row["reason"] = (
                    "no_otello_public_price" if not a else "no_competitor_public_price"
                ) if price_scope == "public" else (
                    "no_otello_price" if not a else "no_competitor_price"
                )
                row["missing_status"] = status
            elif a.observed_scenario is None or b.observed_scenario is None or (
                a.observed_scenario.signature() != b.observed_scenario.signature()
            ):
                row["reason"] = "scenario_mismatch"
            elif hotel.mapping_notes.get(platform) or hotel.mapping_notes.get(Platform.OTELLO):
                row["reason"] = "mapping_disputed"
            elif a.registration and b.registration and a.registration.key() != b.registration.key():
                row["reason"] = "registry_conflict"
            elif any(o.taxes_included is False or o.source_fragments.get("additional_fees")
                     for o in (a, b)):
                row["reason"] = "separate_fees"
            else:
                assert a_total is not None and b_total is not None
                delta = a_total - b_total
                row.update(
                    absolute_gap=str(delta),
                    percent_gap=str((delta / b_total * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )),
                    outcome="loss" if delta > 0 else "win" if delta < 0 else "tie",
                    reason="tariffs_require_review",
                    identity="registry_equal" if a.registration and b.registration
                    else "unconfirmed",
                )
            rows.append(row)
    return {
        "mode": "preliminary_minima", "price_scope": price_scope,
        "unit": "hotel_competitor",
        "formula": "(Otello - competitor) / competitor * 100",
        "rows": rows,
        "disclaimer": "Минимумы в выбранном типе цен. Условия, доступ и объект требуют проверки. "
        "Не является подтверждённым преимуществом или проигрышем.",
    }


def statistics_bundle(
    offers: list[Offer], config: BatchConfig, observations: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    scopes = {s: preliminary_statistics(offers, config, observations, price_scope=s)
              for s in PRICE_SCOPES}
    # Preserve the public baseline for older consumers; all new views select a scope.
    return {**scopes["public"], "default_scope": "all", "scopes": scopes,
            "verified_rows": verified_statistics(offers, matches)}


def verified_statistics(
    offers: list[Offer], matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    lookup = {o.id: o for o in offers}
    selected: dict[tuple[str, Platform], tuple[Offer, Offer]] = {}
    for match in matches:
        if match["percent_gap"] is None:
            continue
        a, b = lookup[match["reference_offer_id"]], lookup[match["competitor_offer_id"]]
        if a.hotel_canonical_id is None:
            continue
        if a.public_total is None or b.public_total is None or b.public_total <= 0:
            continue
        key = (a.hotel_canonical_id, b.platform)
        old = selected.get(key)
        if old is None or (a.public_total, b.public_total) < (
            old[0].public_total or Decimal(0), old[1].public_total or Decimal(0)
        ):
            selected[key] = (a, b)
    rows = []
    for (hotel_id, platform), (a, b) in selected.items():
        assert a.public_total is not None and b.public_total is not None
        delta = a.public_total - b.public_total
        rows.append(dict(
            hotel_id=hotel_id, platform=platform.value, reference_offer_id=a.id,
            competitor_offer_id=b.id, reference_total=str(a.public_total),
            competitor_total=str(b.public_total), absolute_gap=str(delta),
            percent_gap=str((delta / b.public_total * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )), outcome="loss" if delta > 0 else "win" if delta < 0 else "tie",
            reason="verified", identity="registry_equal",
        ))
    return rows
