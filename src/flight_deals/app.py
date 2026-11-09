"""One daily run: search, compare against history, alert on new deals."""

import logging
from datetime import datetime, timedelta

from flight_deals.config import Config
from flight_deals.deals import evaluate
from flight_deals.models import Deal
from flight_deals.notify import Notifier
from flight_deals.sources import FlightSource
from flight_deals.store import Store

log = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    pass


def run(
    config: Config,
    source: FlightSource,
    store: Store,
    notifier: Notifier,
    now: datetime,
) -> list[Deal]:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = store.searches_since(month_start)
    if used >= config.monthly_search_limit:
        raise BudgetExceeded(f"monthly search limit reached ({used}/{config.monthly_search_limit})")

    # Record before calling so a crash mid-request still counts against the budget.
    store.record_search(source.name, now)
    fares = source.explore(config.origins)
    log.info("%s returned %d priced destinations", source.name, len(fares))

    history_since = now - timedelta(days=config.history_days)
    cooldown_since = now - timedelta(days=config.alert_cooldown_days)
    deals = []
    for fare in fares:
        # History is read before today's fares are stored, so a fare never counts towards
        # its own baseline.
        history = store.price_history(fare.airport, fare.currency, history_since)
        deal = evaluate(fare, history, config.rules)
        if deal is None:
            continue
        previous = store.lowest_alert_since(fare.airport, fare.currency, cooldown_since)
        if previous is not None and fare.price >= previous:
            log.info("skipping %s at %d: already alerted at %d", fare.airport, fare.price, previous)
            continue
        deals.append(deal)

    store.record_fares(fares, now)

    deals.sort(key=lambda d: d.fare.price)
    if deals:
        notifier.send(deals)
        # Only after a successful send, so a failed notification is retried next run.
        store.record_alerts(deals, now)
    return deals
