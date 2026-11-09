from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_fare

from flight_deals.app import BudgetExceeded, run
from flight_deals.config import Config
from flight_deals.deals import DealRules
from flight_deals.sources import SourceError

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=UTC)


def make_config(**overrides) -> Config:
    fields = {
        "origins": ("LHR", "MAN"),
        "currency": "GBP",
        "rules": DealRules(max_price=40, min_drop_pct=25, min_history=5),
        "history_days": 60,
        "alert_cooldown_days": 14,
        "monthly_search_limit": 10,
        "db_path": Path("unused.db"),
    } | overrides
    return Config(**fields)


class FakeSource:
    name = "fake"

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def explore(self, origins):
        self.calls += 1
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

    deals = run(make_config(), source, store, notifier, NOW)

    assert [d.fare.airport for d in deals] == ["DUB", "ORK"]
    assert notifier.sent == [deals]
    assert store.searches_since(NOW - timedelta(hours=1)) == 1


def test_same_deal_not_repeated_unless_price_drops(store):
    source = FakeSource([make_fare("ORK", 38)], [make_fare("ORK", 38)], [make_fare("ORK", 30)])
    notifier = RecordingNotifier()
    config = make_config()

    run(config, source, store, notifier, NOW)
    assert run(config, source, store, notifier, NOW + timedelta(days=1)) == []
    cheaper = run(config, source, store, notifier, NOW + timedelta(days=2))

    assert [d.fare.price for d in cheaper] == [30]
    assert len(notifier.sent) == 2


def test_drop_against_own_history_is_a_deal(store):
    store.record_fares([make_fare("BCN", 100)] * 5, NOW - timedelta(days=5))
    source = FakeSource([make_fare("BCN", 70)])

    deals = run(make_config(), source, store, RecordingNotifier(), NOW)

    assert len(deals) == 1
    assert deals[0].typical_price == 100


def test_budget_exhausted_stops_before_calling_source(store):
    for _ in range(10):
        store.record_search("fake", NOW.replace(day=2))
    source = FakeSource()

    with pytest.raises(BudgetExceeded):
        run(make_config(), source, store, RecordingNotifier(), NOW)
    assert source.calls == 0


def test_budget_resets_each_month(store):
    for _ in range(10):
        store.record_search("fake", NOW.replace(month=10))

    run(make_config(), FakeSource([]), store, RecordingNotifier(), NOW)


def test_failed_search_still_counts_against_budget(store):
    source = FakeSource(SourceError("boom"))

    with pytest.raises(SourceError):
        run(make_config(), source, store, RecordingNotifier(), NOW)
    assert store.searches_since(NOW - timedelta(hours=1)) == 1


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
