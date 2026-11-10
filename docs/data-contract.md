# Data contract

Executable schema: `src/rate_shopper/domain/models.py`. All models reject extra fields.
Scenario validates positive adult/room counts, child ages 0–17, RUB and checkout after checkin;
night count is derived, never separately trusted. Guest signatures compare child ages as a multiset.
HotelEntity separates canonical identity from platform mappings and their verification state.
RawObservation records URLs, timestamp, auth state, capture method, hashes, paths and connector errors.
Offer includes raw/normalized room, bed, area, meal, cancellation deadline, payment timing,
all five independent price types, taxes, access, explicit status, fragments and extraction confidence.
Missing facts remain null. Recognized meal/cancellation/payment/access/basis values are constrained.
Price strings deserialize to Decimal; float money and negative values are invalid.
AVAILABLE with no positive public total fails the quality gate, rather than borrowing another price.
`special_payment_product` describes a requirement of the selected tariff, not an alternate bank price.

Additional Offer fields: price_basis, access_type, observed_scenario, url_scenario.
Observed scenario must verify page/form parameters; URL scenario is checked when supplied.
M1 does not parse website URLs. Future connectors must supply parsed URL parameters whenever present.
Source fragments are keyed by field; synthetic paths identify domain fixture values only.
The fixture importer explicitly refuses observed provenance. Real evidence needs a source-specific parser.

OfferMatch has IDs, quality, bounded confidence, differences, optional gaps, review flag,
matcher version and timestamp. Decimal JSON values are strings. CSV empty gaps mean unresolved,
never zero; explicit reasons and statuses are preserved in JSON. Evidence SHA-256 identifies input bytes.

Fixture requires provenance=synthetic, assumptions, scenario, hotels, offers and expected count.
Offers have unique IDs and observation IDs; canonical IDs must be registered or unresolved.
Metrics cover counts, statuses, confidence bands, reviews, connector/scenario failures.
Rates are exact numerator/denominator strings (0/0 means no applicable matches).
Duration is execution telemetry in attempts.jsonl, not a mutable part of a replayable report.
