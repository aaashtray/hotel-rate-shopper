from rate_shopper.domain.models import Offer


def normalize(offer: Offer) -> Offer:
    """Input contract already canonical; never infer a price or unresolved tariff field."""
    return offer
