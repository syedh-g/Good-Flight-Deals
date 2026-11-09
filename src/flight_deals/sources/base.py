from collections.abc import Sequence
from typing import Protocol

from flight_deals.models import Fare, SearchSpec


class SourceError(Exception):
    """A flight source failed to return usable data."""


class FlightSource(Protocol):
    name: str

    def explore(self, origins: Sequence[str], spec: SearchSpec) -> list[Fare]:
        """Return the cheapest fare per destination reachable from any of `origins`.

        Sources should push as much of `spec` to the provider as it supports, but callers
        still filter with `spec.accepts`. Each call counts as one search against the budget.
        """
        ...
