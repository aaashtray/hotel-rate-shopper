"""Exploratory minima, explicitly separate from verified tariff matching.

User authorized this mode on 2026-11-10. Positive gap means Otello costs more.
No personal/bank prices, known extra fees or disputed identities enter the gap.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from rate_shopper.domain.capture import BatchConfig
from rate_shopper.domain.models import Offer, Platform


def preliminary_statistics(
    offers: list[Offer], config: BatchConfig, observations: list[dict[str, Any]]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    obs = {(o["hotel_id"], o["platform"]): o for o in observations}
    for hotel in config.hotels:
        cheapest: dict[Platform, Offer] = {}
        for platform in config.platforms:
            pool = [o for o in offers if o.hotel_canonical_id == hotel.id
                    and o.platform == platform and o.access_type == "public"
                    and o.authorization_required is False and o.public_total is not None
                    and o.public_total > 0 and o.currency == "RUB"
                    and o.price_basis == "stay_total"]
            if pool:
                cheapest[platform] = min(pool, key=lambda o: (o.public_total or Decimal(0), o.id))
        a = cheapest.get(Platform.OTELLO)
        for platform in config.platforms:
            if platform == Platform.OTELLO:
                continue
            b = cheapest.get(platform)
            row: dict[str, Any] = {
                "hotel_id": hotel.id, "platform": platform.value,
                "reference_offer_id": a.id if a else None,
                "competitor_offer_id": b.id if b else None,
                "reference_total": str(a.public_total) if a else None,
                "competitor_total": str(b.public_total) if b else None,
                "absolute_gap": None, "percent_gap": None, "outcome": "excluded",
                "reason": "", "identity": "unconfirmed",
            }
            if not a or not b:
                missing = Platform.OTELLO if not a else platform
                status = obs.get((hotel.id, missing), {}).get("status", "UNKNOWN")
                row["reason"] = (
                    "no_otello_public_price" if not a else "no_competitor_public_price"
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
                assert a.public_total is not None and b.public_total is not None
                delta = a.public_total - b.public_total
                row.update(
                    absolute_gap=str(delta),
                    percent_gap=str((delta / b.public_total * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )),
                    outcome="loss" if delta > 0 else "win" if delta < 0 else "tie",
                    reason="different_tariffs_require_review",
                    identity="registry_equal" if a.registration and b.registration
                    else "unconfirmed",
                )
            rows.append(row)
    return {
        "mode": "preliminary_public_minima",
        "unit": "hotel_competitor",
        "formula": "(Otello - competitor) / competitor * 100",
        "rows": rows,
        "disclaimer": "Минимумы разных публичных тарифов. Условия и объект требуют проверки. "
        "Не является подтверждённым преимуществом или проигрышем.",
    }


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
