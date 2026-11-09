from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_fare

from flight_deals.models import Deal
from flight_deals.store import Store

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)


def test_price_history_filters_by_airport_currency_and_age(store):
    store.record_fares([make_fare("ORK", 50), make_fare("DUB", 40)], NOW - timedelta(days=90))
    store.record_fares([make_fare("ORK", 60), make_fare("ORK", 70, currency="EUR")], NOW)

    assert store.price_history("ORK", "GBP", NOW - timedelta(days=30)) == [60]
    assert sorted(store.price_history("ORK", "GBP", NOW - timedelta(days=365))) == [50, 60]


def test_searches_since(store):
    store.record_search("serpapi", NOW - timedelta(days=40))
    store.record_search("serpapi", NOW)
    assert store.searches_since(NOW - timedelta(days=1)) == 1


def test_lowest_alert_since(store):
    store.record_alerts([Deal(make_fare(price=39), "x", None)], NOW - timedelta(days=3))
    store.record_alerts([Deal(make_fare(price=35), "x", None)], NOW - timedelta(days=30))

    assert store.lowest_alert_since("ORK", "GBP", NOW - timedelta(days=14)) == 39
    assert store.lowest_alert_since("DUB", "GBP", NOW - timedelta(days=14)) is None


def test_reopening_existing_database_keeps_data(tmp_path):
    path = tmp_path / "nested" / "deals.db"
    with Store.open(path) as s:
        s.record_search("serpapi", NOW)
    with Store.open(path) as s:
        assert s.searches_since(NOW - timedelta(days=1)) == 1


def test_naive_timestamps_rejected(store):
    with pytest.raises(ValueError):
        store.record_search("serpapi", datetime(2026, 11, 9))
