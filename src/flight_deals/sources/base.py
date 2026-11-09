from collections.abc import Sequence
from typing import Protocol

from flight_deals.models import Fare


class SourceError(Exception):
    """A flight source failed to return usable data."""


class FlightSource(Protocol):
    name: str

    def explore(self, origins: Sequence[str]) -> list[Fare]:
        """Return the cheapest fare per destination reachable from any of `origins`.

        Each call counts as one search against the monthly budget.
        """
        ...
