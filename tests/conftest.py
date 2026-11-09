from datetime import date

import pytest

from flight_deals.models import Fare, SearchSpec, TripLength
from flight_deals.store import Store


def make_fare(airport: str = "ORK", price: int = 50, **overrides) -> Fare:
    fields = {
        "destination": "Cork",
        "country": "Ireland",
        "airport": airport,
        "price": price,
        "currency": "GBP",
        "outbound": date(2026, 11, 16),
        "inbound": date(2026, 11, 24),
        "airline": "Ryanair",
        "stops": 0,
        "duration_min": 75,
        "link": None,
    } | overrides
    return Fare(**fields)


def make_spec(name: str = "europe", **overrides) -> SearchSpec:
    fields = {
        "name": name,
        "region": None,
        "trip_length": TripLength.ONE_WEEK,
        "max_stops": None,
        "min_duration_min": None,
        "max_duration_min": None,
        "max_price": 40,
    } | overrides
    return SearchSpec(**fields)


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        yield s
