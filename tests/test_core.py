import copy
import json
import sqlite3
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from rate_shopper.domain.models import Fixture, Offer, Scenario
from rate_shopper.evidence.store import EvidenceStore
from rate_shopper.matching.rules import match
from rate_shopper.pipeline import run
from rate_shopper.quality.gates import issues

FIXTURE = Path(__file__).parent / "fixtures/synthetic/reference.json"


@pytest.fixture
def fixture() -> Fixture:
    return Fixture.model_validate_json(FIXTURE.read_bytes())


def test_reference_cases(tmp_path: Path) -> None:
    report = run(FIXTURE, tmp_path)
    matches = {m["competitor_offer_id"]: m for m in report["matches"]}
    assert matches["savoy-yandex"]["absolute_gap"] == "-3000.00"
    assert matches["savoy-yandex"]["percent_gap"] == "-10.00"
    assert matches["savoy-ozon"]["absolute_gap"] == "-6357.00"
    assert matches["savoy-ozon"]["percent_gap"] == "-21.19"
    assert matches["cosmos-ozon"]["percent_gap"] == "0.00"
    assert matches["cosmos-yandex"]["absolute_gap"] == "0.00"
    for key in ["sunflower-ozon", "safmar-ozon", "discovery-yandex", "discovery-ozon"]:
        assert matches[key]["percent_gap"] is None
        assert matches[key]["manual_review_required"]
    sold = next(o for o in report["offers"] if o["id"] == "safmar-ozon")
    assert sold["availability_status"] == "SOLD_OUT"
    assert sold["public_total"] is None
    assert report["status"] == "PARTIAL_SUCCESS"


@pytest.mark.parametrize(
    "change",
    [
        {"checkout": "2026-11-20"},
        {"adults": 0},
        {"rooms": 0},
        {"children_ages": [-1]},
        {"currency": "USD"},
    ],
)
def test_invalid_scenario(fixture: Fixture, change: dict[str, object]) -> None:
    data = fixture.scenario.model_dump()
    data.update(change)
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


@pytest.mark.parametrize(
    "change",
    [
        {"public_total": None, "bank_product_total": "1.00"},
        {"public_total": None, "member_total": "1.00"},
        {"public_total": "0.00"},
        {"price_basis": "night"},
        {"taxes_included": None},
        {"currency": "USD"},
        {"authorization_required": True},
        {"access_type": "bank"},
        {"cancellation_deadline": None},
        {"bed_type": None},
        {"payment_timing": None},
        {"hotel_canonical_id": None},
        {"observed_scenario": None},
        {"extraction_confidence": "0.89"},
        {"source_fragments": {}},
        {"special_conditions": ["mobile only"]},
        {"meal_plan": "breakfast"},
    ],
)
def test_unsafe_comparisons(fixture: Fixture, change: dict[str, object]) -> None:
    data = fixture.offers[1].model_dump()
    data.update(change)
    competitor = Offer.model_validate(data)
    result = match(fixture.offers[0], competitor, fixture.scenario, fixture.scenario.created_at)
    assert result.percent_gap is None
    assert result.manual_review_required


def test_float_rejected(fixture: Fixture) -> None:
    data = fixture.offers[0].model_dump()
    data["public_total"] = 30000.1
    with pytest.raises(ValidationError):
        Offer.model_validate(data)
    assert isinstance(fixture.offers[0].public_total, Decimal)
    assert fixture.scenario.nights == 2


@pytest.mark.parametrize("field", ["observed_scenario", "url_scenario"])
def test_scenario_mismatch(fixture: Fixture, field: str) -> None:
    data = fixture.offers[1].model_dump()
    changed = fixture.scenario.model_dump()
    changed["adults"] = 3
    data[field] = changed
    assert any("mismatch" in i for i in issues(Offer.model_validate(data), fixture.scenario))


def test_replay_and_history(tmp_path: Path) -> None:
    first = run(FIXTURE, tmp_path)
    assert first == run(FIXTURE, tmp_path)
    data = json.loads(FIXTURE.read_text())
    data["offers"][0]["public_total"] = "31000.00"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(data))
    second = run(changed, tmp_path)
    assert second["run_id"] != first["run_id"]
    with sqlite3.connect(tmp_path / "history.sqlite3") as db:
        rows = db.execute("SELECT payload FROM runs").fetchall()
    assert len(rows) == 2
    assert {json.loads(r[0])["offers"][0]["public_total"] for r in rows} == {"30000.00", "31000.00"}
    assert len(list((tmp_path / "evidence").glob("*.json"))) == 2


def test_all_failed(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text())
    for offer in data["offers"]:
        offer["availability_status"] = "CAPTCHA"
        offer["public_total"] = None
    path = tmp_path / "failed.json"
    path.write_text(json.dumps(data))
    report = run(path, tmp_path / "out")
    assert report["status"] == "FAILED"
    assert report["metrics"]["successful_observations"] == 0


def test_cli(tmp_path: Path) -> None:
    result = subprocess.run(
        ["rate-shopper", str(FIXTURE), "--output", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "SOLD_OUT" in result.stdout
    assert "SYNTHETIC" in result.stdout
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.csv").exists()
    assert json.loads((tmp_path / "attempts.jsonl").read_text())["duration_seconds"] > 0


def test_evidence_integrity(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    digest, path = store.save(b"synthetic")
    assert store.save(b"synthetic")[0] == digest
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.save(b"synthetic")


@pytest.mark.parametrize("platform", ["otello", "yandex_travel", "ozon_travel"])
def test_domain_parser_contract(platform: str, fixture: Fixture) -> None:
    assert len([o for o in fixture.offers if o.platform == platform]) == 5
    data = json.loads(FIXTURE.read_text())
    data["offers"][0]["unexpected_layout_field"] = "changed"
    with pytest.raises(ValidationError):
        Fixture.model_validate(data)


def test_missing_conditions_do_not_inherit_assumptions(fixture: Fixture) -> None:
    data = fixture.offers[1].model_dump()
    del data["payment_timing"]
    candidate = Offer.model_validate(data)
    result = match(fixture.offers[0], candidate, fixture.scenario, fixture.scenario.created_at)
    assert result.percent_gap is None


def test_success_and_missing_observations(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text())
    data["offers"] = data["offers"][:6]
    data["expected_observations"] = 6
    source = tmp_path / "subset.json"
    source.write_text(json.dumps(data))
    assert run(source, tmp_path / "out")["status"] == "SUCCESS"
    data["expected_observations"] = 7
    source.write_text(json.dumps(data))
    assert run(source, tmp_path / "out")["status"] == "PARTIAL_SUCCESS"


def test_duplicate_offer_rejected(fixture: Fixture) -> None:
    data = fixture.model_dump()
    data["offers"] = [data["offers"][0], copy.deepcopy(data["offers"][0])]
    with pytest.raises(ValidationError):
        Fixture.model_validate(data)


@pytest.mark.parametrize(
    "state",
    [
        "SOLD_OUT",
        "HOTEL_NOT_FOUND",
        "PRICE_NOT_EXPOSED",
        "AUTH_REQUIRED",
        "CAPTCHA",
        "RATE_LIMITED",
        "CONNECTOR_ERROR",
        "PARSE_ERROR",
        "SCENARIO_MISMATCH",
        "UNKNOWN",
    ],
)
def test_unavailable_states_never_have_gaps(fixture: Fixture, state: str) -> None:
    data = fixture.offers[1].model_dump()
    data.update(availability_status=state, public_total=None)
    result = match(
        fixture.offers[0], Offer.model_validate(data), fixture.scenario, fixture.scenario.created_at
    )
    assert result.absolute_gap is None
    assert result.percent_gap is None
    assert any(state in difference for difference in result.differences)


def test_public_not_lowest_price(fixture: Fixture) -> None:
    data = fixture.offers[2].model_dump()
    data.update(bank_product_total="1.00", member_total="2.00", mobile_total="3.00")
    result = match(
        fixture.offers[0], Offer.model_validate(data), fixture.scenario, fixture.scenario.created_at
    )
    assert result.absolute_gap == Decimal("-6357.00")


def test_cancellation_deadlines_must_match(fixture: Fixture) -> None:
    data = fixture.offers[1].model_dump()
    data["cancellation_deadline"] = "2026-11-17T18:00:00+03:00"
    result = match(
        fixture.offers[0], Offer.model_validate(data), fixture.scenario, fixture.scenario.created_at
    )
    assert result.percent_gap is None
    assert "different cancellation deadline" in result.differences


def test_empty_batch_is_failed(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text())
    data["offers"] = []
    source = tmp_path / "empty.json"
    source.write_text(json.dumps(data))
    assert run(source, tmp_path / "out")["status"] == "FAILED"


def test_strong_match_with_unknown_area(fixture: Fixture) -> None:
    data = fixture.offers[1].model_dump()
    data["room_area_m2"] = None
    result = match(
        fixture.offers[0], Offer.model_validate(data), fixture.scenario, fixture.scenario.created_at
    )
    assert result.match_quality == "strong"
    assert result.match_confidence == Decimal(".95")
    assert result.percent_gap == Decimal("-10.00")
