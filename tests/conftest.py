from datetime import date

import pytest

from flight_deals.models import Fare
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


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        yield s
