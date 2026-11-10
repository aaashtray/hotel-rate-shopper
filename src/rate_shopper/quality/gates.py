from rate_shopper.domain.models import Offer, Scenario, Status

KEY_FIELDS = (
    "room_category_normalized",
    "bed_type",
    "meal_plan",
    "cancellation_type",
    "payment_timing",
    "taxes_included",
    "access_type",
    "price_basis",
    "authorization_required",
)


def issues(offer: Offer, scenario: Scenario) -> list[str]:
    result: list[str] = []
    if offer.scenario_id != scenario.id:
        result.append("scenario ID mismatch")
    if offer.observed_scenario is None:
        result.append("page/form scenario unverified")
    elif offer.observed_scenario.signature() != scenario.signature():
        result.append("page/form scenario mismatch")
    if offer.url_scenario and offer.url_scenario.signature() != scenario.signature():
        result.append("URL scenario mismatch")
    if offer.currency != scenario.currency:
        result.append("currency mismatch")
    if offer.hotel_canonical_id is None:
        result.append("hotel identity unresolved")
    if offer.availability_status != Status.AVAILABLE:
        result.append(f"availability: {offer.availability_status}")
        return result
    if offer.public_total is None or offer.public_total <= 0:
        result.append("positive public total missing")
    if offer.price_basis != "stay_total":
        result.append("whole-stay total unverified")
    if offer.access_type != "public" or offer.authorization_required is not False:
        result.append("public access unverified")
    if offer.loyalty_program or offer.special_payment_product or offer.special_conditions:
        result.append("special access or conditions require review")
    if offer.taxes_included is not True:
        result.append("all-in taxes unverified")
    if offer.bed_type == "allocation_not_guaranteed":
        result.append("bed allocation not guaranteed")
    for field in KEY_FIELDS:
        if getattr(offer, field) is None:
            result.append(f"unresolved: {field}")
    if offer.cancellation_type == "free" and offer.cancellation_deadline is None:
        result.append("free cancellation deadline unresolved")
    required = (
        *KEY_FIELDS,
        "public_total",
        "observed_scenario",
        "hotel_canonical_id",
        "availability_status",
    )
    for field in required:
        if not offer.source_fragments.get(field):
            result.append(f"evidence missing: {field}")
    if offer.cancellation_type == "free" and not offer.source_fragments.get(
        "cancellation_deadline"
    ):
        result.append("evidence missing: cancellation_deadline")
    return result
