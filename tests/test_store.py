import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest
from conftest import make_fare

from flight_deals.models import Deal
from flight_deals.store import _MIGRATIONS, Store

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
TODAY = NOW.replace(hour=0)


def unscored(*fares):
    return [(f, None) for f in fares]


def test_daily_lows_takes_cheapest_per_day_in_window(store):
    store.record_fares("europe", unscored(make_fare("ORK", 50)), NOW - timedelta(days=90))
    store.record_fares("europe", unscored(make_fare("ORK", 60)), NOW - timedelta(days=2, hours=3))
    store.record_fares("europe", unscored(make_fare("ORK", 55)), NOW - timedelta(days=2, hours=1))
    store.record_fares("europe", unscored(make_fare("ORK", 70)), NOW - timedelta(days=1))
    store.record_fares("europe", unscored(make_fare("ORK", 10)), NOW)  # today: excluded

    assert store.daily_lows("europe", "ORK", "GBP", TODAY - timedelta(days=30), TODAY) == [55, 70]


def test_daily_lows_filters_by_search_airport_and_currency(store):
    day = NOW - timedelta(days=1)
    store.record_fares("europe", unscored(make_fare("ORK", 60)), day)
    store.record_fares("europe", unscored(make_fare("ORK", 70, currency="EUR")), day)
    store.record_fares("europe", unscored(make_fare("DUB", 40)), day)
    store.record_fares("asia", unscored(make_fare("ORK", 99)), day)

    since = TODAY - timedelta(days=30)
    assert store.daily_lows("europe", "ORK", "GBP", since, TODAY) == [60]
    assert store.daily_lows("asia", "ORK", "GBP", since, TODAY) == [99]


def test_timestamps_are_normalised_to_utc(store):
    # 00:30 on the 9th in UTC+2 is still the 8th in UTC.
    plus_two = datetime(2026, 11, 9, 0, 30, tzinfo=timezone(timedelta(hours=2)))
    store.record_fares("europe", unscored(make_fare("ORK", 60)), plus_two)

    assert store.daily_lows("europe", "ORK", "GBP", TODAY - timedelta(days=1), TODAY) == [60]


def test_zscore_is_stored(store):
    store.record_fares("europe", [(make_fare("ORK", 60), -1.5)], NOW)
    (zscore,) = store._conn.execute("SELECT zscore FROM observations").fetchone()
    assert zscore == -1.5


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


def test_v1_observations_migrate_into_europe_history(tmp_path):
    path = tmp_path / "deals.db"
    conn = sqlite3.connect(path)
    conn.executescript(_MIGRATIONS[0])
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        """
        INSERT INTO observations (observed_at, airport, destination, country, price, currency,
                                  outbound, inbound, airline, stops)
        VALUES (?, 'ORK', 'Cork', 'Ireland', 32, 'GBP', '2026-11-16', '2026-11-24', 'Ryanair', 0)
        """,
        ((NOW - timedelta(days=1)).isoformat(timespec="seconds"),),
    )
    conn.commit()
    conn.close()

    with Store.open(path) as s:
        assert s.daily_lows("europe", "ORK", "GBP", TODAY - timedelta(days=7), TODAY) == [32]
        assert s._conn.execute("PRAGMA user_version").fetchone()[0] == len(_MIGRATIONS)


def test_naive_timestamps_rejected(store):
    with pytest.raises(ValueError):
        store.record_search("serpapi", datetime(2026, 11, 9))
