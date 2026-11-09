from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_fare, make_spec

from flight_deals.app import BudgetExceeded, run
from flight_deals.config import Config
from flight_deals.deals import DealRules
from flight_deals.sources import SourceError

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)


def make_config(**overrides) -> Config:
    fields = {
        "origins": ("LHR", "MAN"),
        "currency": "GBP",
        "searches": (make_spec("europe"),),
        "rules": DealRules(min_zscore=2.0, min_saving_pct=12, min_history_days=7, min_spread_pct=5),
        "history_days": 60,
        "alert_cooldown_days": 14,
        "monthly_search_limit": 10,
        "db_path": Path("unused.db"),
    } | overrides
    return Config(**fields)


def seed_history(store, search, airport, prices):
    """Record one price per day for the days before NOW."""
    for days_ago, price in enumerate(reversed(prices), start=1):
        store.record_fares(search, [(make_fare(airport, price), None)], NOW - timedelta(days_ago))


class FakeSource:
    """Returns queued responses in order; an Exception response is raised instead."""

    name = "fake"

    def __init__(self, *responses):
        self._responses = list(responses)
        self.specs = []

    def explore(self, origins, spec):
        self.specs.append(spec.name)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, deals):
        self.sent.append(list(deals))


def test_alerts_cheap_fares_sorted_by_price(store):
    source = FakeSource([make_fare("ORK", 38), make_fare("DUB", 32), make_fare("BCN", 90)])
    notifier = RecordingNotifier()

    result = run(make_config(), source, store, notifier, NOW)

    assert [d.fare.airport for d in result.deals] == ["DUB", "ORK"]
    assert result.failed_searches == []
    assert notifier.sent == [result.deals]
    assert store.searches_since(NOW - timedelta(hours=1)) == 1


def test_runs_every_configured_search(store):
    config = make_config(searches=(make_spec("europe"), make_spec("asia")))
    source = FakeSource([make_fare("ORK", 38)], [make_fare("BKK", 30)])

    result = run(config, source, store, RecordingNotifier(), NOW)

    assert source.specs == ["europe", "asia"]
    assert [d.fare.airport for d in result.deals] == ["BKK", "ORK"]
    assert store.searches_since(NOW - timedelta(hours=1)) == 2


def test_fares_outside_spec_are_ignored_and_not_stored(store):
    spec = make_spec("asia", max_stops=1, min_duration_min=300)
    source = FakeSource(
        [
            make_fare("AYT", 20, duration_min=255),  # too short
            make_fare("HKG", 20, duration_min=900, stops=2),  # too many stops
            make_fare("BKK", 20, duration_min=900, stops=1),
        ]
    )

    result = run(make_config(searches=(spec,)), source, store, RecordingNotifier(), NOW)

    assert [d.fare.airport for d in result.deals] == ["BKK"]
    tomorrow = NOW + timedelta(days=1)
    assert store.daily_lows("asia", "AYT", "GBP", NOW - timedelta(days=1), tomorrow) == []
    assert store.daily_lows("asia", "BKK", "GBP", NOW - timedelta(days=1), tomorrow) == [20]


def test_same_airport_from_two_searches_alerts_once_at_cheapest(store):
    config = make_config(searches=(make_spec("europe"), make_spec("asia")))
    source = FakeSource([make_fare("TLV", 38)], [make_fare("TLV", 35)])

    result = run(config, source, store, RecordingNotifier(), NOW)

    assert [(d.fare.airport, d.fare.price) for d in result.deals] == [("TLV", 35)]


def test_same_deal_not_repeated_unless_price_drops(store):
    source = FakeSource([make_fare("ORK", 38)], [make_fare("ORK", 38)], [make_fare("ORK", 30)])
    notifier = RecordingNotifier()
    config = make_config()

    run(config, source, store, notifier, NOW)
    assert run(config, source, store, notifier, NOW + timedelta(days=1)).deals == []
    cheaper = run(config, source, store, notifier, NOW + timedelta(days=2))

    assert [d.fare.price for d in cheaper.deals] == [30]
    assert len(notifier.sent) == 2


def test_unusual_drop_against_own_history_is_a_deal(store):
    seed_history(store, "europe", "BCN", [100, 98, 102, 100, 101, 99, 100])
    source = FakeSource([make_fare("BCN", 80)])

    result = run(make_config(), source, store, RecordingNotifier(), NOW)

    assert len(result.deals) == 1
    assert result.deals[0].typical_price == pytest.approx(100)
    assert result.deals[0].reason.startswith("usually £100")


def test_history_from_another_search_is_not_used(store):
    seed_history(store, "asia", "BCN", [100] * 7)
    source = FakeSource([make_fare("BCN", 80)])

    assert run(make_config(), source, store, RecordingNotifier(), NOW).deals == []


def test_earlier_run_today_does_not_count_as_history(store):
    seed_history(store, "europe", "BCN", [100] * 6)
    config = make_config()
    run(config, FakeSource([make_fare("BCN", 100)]), store, RecordingNotifier(), NOW)

    # Only 6 whole days of history, so still no baseline later the same day.
    later = run(
        config, FakeSource([make_fare("BCN", 80)]), store, RecordingNotifier(), NOW.replace(hour=20)
    )
    assert later.deals == []


def test_every_fare_is_stored_with_its_score(store):
    seed_history(store, "europe", "BCN", [100] * 7)
    run(
        make_config(),
        FakeSource([make_fare("BCN", 90), make_fare("NEW", 90)]),
        store,
        RecordingNotifier(),
        NOW,
    )

    rows = dict(
        store._conn.execute(
            "SELECT airport, zscore FROM observations WHERE observed_at = ?",
            (NOW.isoformat(timespec="seconds"),),
        ).fetchall()
    )
    assert rows["BCN"] == pytest.approx(-2.1, abs=0.05)
    assert rows["NEW"] is None


def test_budget_must_cover_the_whole_run(store):
    for _ in range(9):
        store.record_search("fake", NOW.replace(day=2))
    config = make_config(searches=(make_spec("europe"), make_spec("asia")))
    source = FakeSource()

    with pytest.raises(BudgetExceeded, match="needs 2 searches but only 1"):
        run(config, source, store, RecordingNotifier(), NOW)
    assert source.specs == []


def test_budget_resets_each_month(store):
    for _ in range(10):
        store.record_search("fake", NOW.replace(month=10))

    run(make_config(), FakeSource([]), store, RecordingNotifier(), NOW)


def test_one_failed_search_does_not_stop_the_others(store):
    config = make_config(searches=(make_spec("europe"), make_spec("asia")))
    source = FakeSource(SourceError("boom"), [make_fare("BKK", 30)])
    notifier = RecordingNotifier()

    result = run(config, source, store, notifier, NOW)

    assert result.failed_searches == ["europe"]
    assert [d.fare.airport for d in result.deals] == ["BKK"]
    assert store.searches_since(NOW - timedelta(hours=1)) == 2


def test_failed_notification_is_retried_next_run(store):
    class FailingNotifier:
        def send(self, deals):
            raise RuntimeError("smtp down")

    source = FakeSource([make_fare("ORK", 38)], [make_fare("ORK", 38)])
    with pytest.raises(RuntimeError):
        run(make_config(), source, store, FailingNotifier(), NOW)

    notifier = RecordingNotifier()
    run(make_config(), source, store, notifier, NOW + timedelta(days=1))
    assert len(notifier.sent) == 1
