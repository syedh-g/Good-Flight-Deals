"""Deciding whether a fare is a deal. Pure functions only — no I/O.

A fare is scored against its own route's history using a robust z-score on log prices:

    z = (log(price) - median(log history)) / spread

where `spread` is the median absolute deviation scaled to match a standard deviation. Log space
makes the score proportional (a £20 drop matters more on £40 than on £600), and median/MAD keep
one glitchy price from distorting the baseline. Routes that normally swing a lot need a bigger
drop to score well; stable routes are flagged on smaller ones.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from statistics import median

from flight_deals.models import Deal, Fare

# Scales MAD to estimate a standard deviation for normally distributed data.
MAD_TO_SIGMA = 1.4826

_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}


@dataclass(frozen=True)
class DealRules:
    min_zscore: float  # how many spreads below typical counts as unusual
    min_saving_pct: float  # and the saving must be at least this big to matter
    min_history_days: int  # days of history before the baseline is trusted
    min_spread_pct: float  # floor on spread, so a flat-priced route doesn't flag £1 dips


@dataclass(frozen=True)
class Baseline:
    """What's normal for one route, from its daily cheapest prices."""

    typical: float
    spread: float  # robust standard deviation of log price
    days: int
    lowest: int

    def zscore(self, price: int) -> float:
        return (math.log(price) - math.log(self.typical)) / self.spread

    def normal_range(self) -> tuple[float, float]:
        """Roughly the middle two-thirds of prices on this route."""
        return self.typical * math.exp(-self.spread), self.typical * math.exp(self.spread)


@dataclass(frozen=True)
class Assessment:
    fare: Fare
    baseline: Baseline | None
    zscore: float | None
    deal: Deal | None


def format_price(amount: float, currency: str) -> str:
    symbol = _SYMBOLS.get(currency)
    return f"{symbol}{amount:,.0f}" if symbol else f"{amount:,.0f} {currency}"


def build_baseline(daily_prices: Sequence[int], rules: DealRules) -> Baseline | None:
    """Baseline from one cheapest price per day, or None if there isn't enough history yet."""
    if len(daily_prices) < rules.min_history_days:
        return None
    logs = [math.log(p) for p in daily_prices]
    centre = median(logs)
    mad = median(abs(x - centre) for x in logs)
    spread = max(MAD_TO_SIGMA * mad, rules.min_spread_pct / 100)
    return Baseline(math.exp(centre), spread, len(daily_prices), min(daily_prices))


def assess(
    fare: Fare, daily_prices: Sequence[int], rules: DealRules, max_price: int | None
) -> Assessment:
    """Score `fare` against its route history and decide whether it's a deal.

    A deal is either unusually cheap for its route (z-score and saving both clear their
    thresholds) or at/below the search's absolute `max_price`. `daily_prices` must not
    include `fare` itself.
    """
    baseline = build_baseline(daily_prices, rules)
    zscore = baseline.zscore(fare.price) if baseline else None

    reason = None
    if baseline is not None and zscore is not None:
        saving_pct = (1 - fare.price / baseline.typical) * 100
        if zscore <= -rules.min_zscore and saving_pct >= rules.min_saving_pct:
            reason = _anomaly_reason(fare, baseline, saving_pct)
    if reason is None and max_price is not None and fare.price <= max_price:
        reason = f"{format_price(max_price, fare.currency)} or less"

    deal = Deal(fare, reason, baseline.typical if baseline else None) if reason else None
    return Assessment(fare, baseline, zscore, deal)


def _anomaly_reason(fare: Fare, baseline: Baseline, saving_pct: float) -> str:
    low, high = baseline.normal_range()
    price = partial(format_price, currency=fare.currency)
    reason = (
        f"usually {price(baseline.typical)} (normally {price(low)}-{price(high)}), "
        f"{saving_pct:.0f}% off"
    )
    if fare.price < baseline.lowest:
        reason += f", lowest in {baseline.days} days tracked"
    return reason
