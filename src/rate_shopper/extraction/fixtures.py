from rate_shopper.domain.models import Fixture


def parse_domain_fixture(content: bytes) -> Fixture:
    """No website response is claimed: this is a synthetic domain fixture parser."""
    return Fixture.model_validate_json(content)
