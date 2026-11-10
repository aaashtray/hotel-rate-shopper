from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from rate_shopper.domain.models import Platform, RawObservation, Status
from rate_shopper.evidence.store import EvidenceStore
from rate_shopper.extraction.fixtures import parse_domain_fixture
from rate_shopper.matching.rules import match
from rate_shopper.normalization.offers import normalize
from rate_shopper.quality.gates import issues
from rate_shopper.storage.history import save_run

PIPELINE_VERSION = "offline-1"


def run(fixture_path: Path, output: Path) -> dict[str, Any]:
    content = fixture_path.read_bytes()
    digest, evidence_path = EvidenceStore(output / "evidence").save(content)
    fixture = parse_domain_fixture(content)
    run_id = f"{PIPELINE_VERSION}-{digest}"
    offers = [normalize(o) for o in fixture.offers]
    observations = [
        RawObservation(
            id=o.observation_id,
            run_id=run_id,
            platform=o.platform,
            scenario_id=o.scenario_id,
            checked_at=fixture.scenario.created_at,
            capture_method="synthetic_domain_fixture",
            auth_state="synthetic",
            connector_version=PIPELINE_VERSION,
            content_hash=digest,
            raw_json_paths=(str(evidence_path.relative_to(output)),),
        )
        for o in offers
    ]
    matches = []
    for reference in offers:
        if reference.platform != Platform.OTELLO:
            continue
        for competitor in offers:
            if competitor.platform == Platform.OTELLO:
                continue
            # Fixture groups use hotel_name_raw only for unresolved review candidates.
            if reference.hotel_canonical_id == competitor.hotel_canonical_id or (
                competitor.hotel_canonical_id is None
                and reference.hotel_name_raw == competitor.hotel_name_raw
            ):
                matches.append(
                    match(reference, competitor, fixture.scenario, fixture.scenario.created_at)
                )
    quality = {o.id: issues(o, fixture.scenario) for o in offers}
    successful = sum(
        not quality[o.id]
        or (
            o.availability_status == Status.SOLD_OUT
            and quality[o.id] == ["availability: SOLD_OUT"]
            and bool(o.source_fragments.get("availability_status"))
        )
        for o in offers
    )
    status = (
        "FAILED"
        if not successful
        else "SUCCESS"
        if successful == fixture.expected_observations
        else "PARTIAL_SUCCESS"
    )
    counts = Counter(o.availability_status.value for o in offers)
    review = [m.id for m in matches if m.manual_review_required]
    mismatch_count = sum(any("scenario" in v for v in values) for values in quality.values())
    report: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "provenance": fixture.provenance,
        "assumptions": list(fixture.assumptions),
        "status": status,
        "scenario": fixture.scenario.model_dump(mode="json"),
        "observations": [o.model_dump(mode="json") for o in observations],
        "offers": [o.model_dump(mode="json") for o in offers],
        "matches": [m.model_dump(mode="json") for m in matches],
        "quality_issues": quality,
        "manual_review_queue": review,
        "metrics": {
            "expected_scenarios": 1,
            "expected_observations": fixture.expected_observations,
            "successful_observations": successful,
            "extracted_offers": len(offers),
            "available": counts["AVAILABLE"],
            "sold_out": counts["SOLD_OUT"],
            "unresolved": len(offers) - successful,
            "high_confidence": sum(m.match_confidence >= Decimal("0.9") for m in matches),
            "medium_confidence": sum(
                Decimal("0.5") <= m.match_confidence < Decimal("0.9") for m in matches
            ),
            "low_confidence": sum(m.match_confidence < Decimal("0.5") for m in matches),
            "manual_review_count": len(review),
            "manual_review_rate": f"{len(review)}/{len(matches)}",
            "connector_errors": counts["CONNECTOR_ERROR"],
            "scenario_mismatch_count": sum(
                any("scenario" in v for v in values) for values in quality.values()
            ),
            "scenario_mismatch_rate": f"{mismatch_count}/{fixture.expected_observations}",
        },
    }
    save_run(output / "history.sqlite3", run_id, report)
    return report
