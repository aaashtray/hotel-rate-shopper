from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from rate_shopper.domain.models import Offer, OfferMatch, Platform, Scenario
from rate_shopper.quality.gates import issues

WEIGHTS = {
    "room_category_normalized": Decimal("0.25"),
    "meal_plan": Decimal("0.20"),
    "cancellation_type": Decimal("0.20"),
    "payment_timing": Decimal("0.15"),
    "bed_type": Decimal("0.15"),
    "room_area_m2": Decimal("0.05"),
}


def match(
    reference: Offer,
    competitor: Offer,
    scenario: Scenario,
    created_at: datetime,
    *,
    require_registration: bool = False,
) -> OfferMatch:
    differences = [f"reference: {i}" for i in issues(reference, scenario)]
    differences += [f"competitor: {i}" for i in issues(competitor, scenario)]
    if reference.platform != Platform.OTELLO or competitor.platform == Platform.OTELLO:
        differences.append("invalid platform direction")
    if reference.hotel_canonical_id != competitor.hotel_canonical_id:
        differences.append("hotel identity mismatch")
    left_id, right_id = reference.registration, competitor.registration
    if left_id and right_id and left_id.key() != right_id.key():
        differences.append("hotel registration mismatch")
    if require_registration and (
        not left_id
        or not right_id
        or left_id.verification_status == "user_supplied"
        or right_id.verification_status == "user_supplied"
    ):
        differences.append("hotel registration not independently confirmed on both sources")
    score = Decimal("1")
    for field, weight in WEIGHTS.items():
        left, right = getattr(reference, field), getattr(competitor, field)
        if left is None or right is None:
            score -= weight
        elif left != right:
            score -= weight
            differences.append(f"different {field}: {left} / {right}")
    if reference.cancellation_deadline != competitor.cancellation_deadline:
        differences.append("different cancellation deadline")
    score = min(score, reference.extraction_confidence, competitor.extraction_confidence)
    if differences:
        score = min(score, Decimal("0.49"))
    if score < Decimal("0.90") and not differences:
        differences.append("confidence below 0.90")
    accepted = not differences
    absolute = percent = None
    if accepted:
        assert reference.public_total is not None and competitor.public_total is not None
        absolute = competitor.public_total - reference.public_total
        percent = ((competitor.public_total / reference.public_total - 1) * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return OfferMatch(
        id=f"{reference.id}--{competitor.id}",
        scenario_id=scenario.id,
        hotel_canonical_id=reference.hotel_canonical_id,
        reference_offer_id=reference.id,
        competitor_offer_id=competitor.id,
        match_quality=("exact" if score == 1 else "strong") if accepted else "rejected",
        match_confidence=score,
        differences=tuple(differences),
        absolute_gap=absolute,
        percent_gap=percent,
        manual_review_required=not accepted,
        created_at=created_at,
    )
