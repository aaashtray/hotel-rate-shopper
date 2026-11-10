from typing import Protocol

from rate_shopper.domain.models import HotelEntity, RawObservation, Scenario


class Connector(Protocol):
    def capture(self, hotel: HotelEntity, scenario: Scenario) -> RawObservation: ...
