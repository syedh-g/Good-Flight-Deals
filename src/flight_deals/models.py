from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Region(StrEnum):
    EUROPE = "europe"
    ASIA = "asia"  # includes the Middle East
    NORTH_AMERICA = "north_america"
    SOUTH_AMERICA = "south_america"
    AFRICA = "africa"
    CARIBBEAN = "caribbean"


class TripLength(StrEnum):
    WEEKEND = "weekend"
    ONE_WEEK = "one_week"
    TWO_WEEKS = "two_weeks"


@dataclass(frozen=True)
class SearchSpec:
    """One named search run each day, e.g. "2-week trips to Asia with at most 1 stop"."""

    name: str
    region: Region | None
    trip_length: TripLength
    max_stops: int | None
    min_duration_min: int | None
    max_duration_min: int | None
    max_price: int | None  # always alert at or below this, whatever the route's history

    def accepts(self, fare: "Fare") -> bool:
        """Whether `fare` satisfies this spec. Sources may not honour every filter, and some
        (like a minimum duration) can't be expressed to the API at all."""
        if self.max_stops is not None and (fare.stops is None or fare.stops > self.max_stops):
            return False
        if self.min_duration_min is not None or self.max_duration_min is not None:
            if fare.duration_min is None:
                return False
            if self.min_duration_min is not None and fare.duration_min < self.min_duration_min:
                return False
            if self.max_duration_min is not None and fare.duration_min > self.max_duration_min:
                return False
        return True


@dataclass(frozen=True)
class Fare:
    """Cheapest return fare found to one destination airport.

    `duration_min` is the one-way journey time, including any layover.
    """

    destination: str
    country: str
    airport: str
    price: int
    currency: str
    outbound: date
    inbound: date
    airline: str | None
    stops: int | None
    duration_min: int | None
    link: str | None


@dataclass(frozen=True)
class Deal:
    fare: Fare
    reason: str
    typical_price: float | None
