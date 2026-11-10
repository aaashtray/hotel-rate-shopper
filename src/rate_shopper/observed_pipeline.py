import hashlib
import json
from pathlib import Path
from typing import Any

from rate_shopper.domain.models import Offer, RawObservation, Scenario, Status
from rate_shopper.extraction.yandex_travel import classify, page_title
from rate_shopper.quality.gates import issues
from rate_shopper.storage.history import save_run


def replay(manifest: Path, output: Path) -> dict[str, Any]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("provenance") != "observed":
        raise ValueError("Expected observed capture manifest")
    scenario = Scenario.model_validate(payload["scenario"])
    observation = RawObservation.model_validate(payload["observation"])
    if observation.scenario_id != scenario.id:
        raise ValueError("Capture scenario ID mismatch")
    if observation.raw_html_path is None:
        raise ValueError("Missing raw HTML evidence")
    raw = (manifest.parent / observation.raw_html_path).resolve()
    if not raw.is_relative_to(manifest.parent.resolve()):
        raise ValueError("Raw evidence path escapes capture directory")
    body = raw.read_bytes()
    if hashlib.sha256(body).hexdigest() != observation.content_hash:
        raise ValueError("Evidence integrity failure")
    status, reason = classify(observation, page_title(body))
    observation = observation.model_copy(update={"captcha_detected": status == Status.CAPTCHA})
    # Status-only normalization is not a room offer and must not count as an extracted tariff.
    normalized = Offer(
        id=f"{observation.id}-status",
        observation_id=observation.id,
        platform=observation.platform,
        scenario_id=scenario.id,
        hotel_canonical_id=None,
        hotel_name_raw="",
        availability_status=status,
        extraction_confidence="0",
        source_url=observation.final_url,
        source_fragments={"availability_status": reason, "page_title": page_title(body)},
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "parser_version": "yandex-blockers-1",
        "provenance": "observed",
        "run_id": f"yandex-blockers-1-{observation.run_id}",
        "status": "FAILED",
        "scenario": scenario.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json"),
        "observation_status": status.value,
        "reason": reason,
        "capture_manifest": str(manifest.resolve()),
        "normalized_status": normalized.model_dump(mode="json"),
        "offers": [],
        "matches": [],
        "quality_issues": issues(normalized, scenario),
        "manual_review_queue": [observation.id],
        "metrics": {
            "expected_scenarios": 1,
            "expected_observations": 1,
            "successful_observations": 0,
            "extracted_offers": 0,
            "available": 0,
            "sold_out": 0,
            "unresolved": 1,
            "connector_errors": int(status == Status.CONNECTOR_ERROR),
            "manual_review_count": 1,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    save_run(output / "history.sqlite3", report["run_id"], report)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
