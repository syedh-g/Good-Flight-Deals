"""One daily run: search, compare against history, alert on new deals."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flight_deals.config import Config
from flight_deals.deals import assess
from flight_deals.models import Deal, SearchSpec
from flight_deals.notify import Notifier
from flight_deals.sources import FlightSource, SourceError
from flight_deals.store import Store

log = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class RunResult:
    deals: list[Deal]
    failed_searches: list[str]


def run(
    config: Config,
    source: FlightSource,
    store: Store,
    notifier: Notifier,
    now: datetime,
) -> RunResult:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = store.searches_since(month_start)
    needed = len(config.searches)
    if used + needed > config.monthly_search_limit:
        raise BudgetExceeded(
            f"run needs {needed} searches but only "
            f"{max(config.monthly_search_limit - used, 0)} of {config.monthly_search_limit} "
            "remain this month"
        )

    deals: list[Deal] = []
    failed: list[str] = []
    for spec in config.searches:
        try:
            deals.extend(_run_search(config, spec, source, store, now))
        except SourceError as e:
            log.error("search %r failed: %s", spec.name, e)
            failed.append(spec.name)

    deals = _cheapest_per_airport(deals)
    if deals:
        notifier.send(deals)
        # Only after a successful send, so a failed notification is retried next run.
        store.record_alerts(deals, now)
    return RunResult(deals, failed)


def _run_search(
    config: Config, spec: SearchSpec, source: FlightSource, store: Store, now: datetime
) -> list[Deal]:
    # Record before calling so a crash mid-request still counts against the budget.
    store.record_search(source.name, now)
    found = source.explore(config.origins, spec)
    fares = [f for f in found if spec.accepts(f)]
    log.info("%s: %d priced destinations, %d match filters", spec.name, len(found), len(fares))

    # Baselines use whole days before today, so a fare never counts towards its own baseline
    # and an earlier run today doesn't skew it.
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    history_since = today - timedelta(days=config.history_days)
    cooldown_since = now - timedelta(days=config.alert_cooldown_days)
    deals = []
    scored = []
    for fare in fares:
        history = store.daily_lows(spec.name, fare.airport, fare.currency, history_since, today)
        assessment = assess(fare, history, config.rules, spec.max_price)
        scored.append((fare, assessment.zscore))
        deal = assessment.deal
        if deal is None:
            continue
        previous = store.lowest_alert_since(fare.airport, fare.currency, cooldown_since)
        if previous is not None and fare.price >= previous:
            log.info("skipping %s at %d: already alerted at %d", fare.airport, fare.price, previous)
            continue
        deals.append(deal)

    store.record_fares(spec.name, scored, now)
    return deals


def _cheapest_per_airport(deals: list[Deal]) -> list[Deal]:
    """Keep one deal per destination when overlapping searches both find it."""
    best: dict[str, Deal] = {}
    for deal in deals:
        current = best.get(deal.fare.airport)
        if current is None or deal.fare.price < current.fare.price:
            best[deal.fare.airport] = deal
    return sorted(best.values(), key=lambda d: d.fare.price)
