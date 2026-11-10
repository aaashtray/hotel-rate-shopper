from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from rate_shopper.domain.models import Fixture, HotelRegistration
from rate_shopper.matching.rules import match
from rate_shopper.reporting.html import write_html

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def reg(value: str = "С782026029186", status: str = "source_observed") -> HotelRegistration:
    return HotelRegistration.model_validate(
        dict(
            registry="ru_accommodation",
            country="RU",
            registration_id=value,
            verification_status=status,
            checked_at=NOW,
            source_url="https://example.test",
            source_text="synthetic evidence",
        )
    )


def test_normalize_latin_c() -> None:
    assert reg("C782026029186").registration_id == "С782026029186"


@pytest.mark.parametrize("value", ["782026029186", "С123", "С7820260291860"])
def test_invalid_registry(value: str) -> None:
    with pytest.raises(ValidationError):
        reg(value)


@pytest.mark.parametrize("mode", ["missing", "conflict", "user_supplied", "same"])
def test_registry_match(mode: str) -> None:
    path = Path(__file__).parent / "fixtures/synthetic/reference.json"
    fixture = Fixture.model_validate_json(path.read_bytes())
    left = next(o for o in fixture.offers if o.id == "savoy-otello")
    right = next(o for o in fixture.offers if o.id == "savoy-ozon")
    if mode != "missing":
        left = left.model_copy(update={"registration": reg()})
        right = right.model_copy(
            update={
                "registration": reg(
                    "С782025003929" if mode == "conflict" else "С782026029186",
                    "user_supplied" if mode == "user_supplied" else "source_observed",
                )
            }
        )
    result = match(left, right, fixture.scenario, NOW, require_registration=True)
    assert (result.percent_gap is not None) == (mode == "same")


def test_html_escapes_source_content(tmp_path: Path) -> None:
    write_html({"unsafe": "</script><img src=x>"}, tmp_path)
    content = (tmp_path / "index.html").read_text()
    assert "</script><img" not in content
    assert "\\u003c/script>" in content
