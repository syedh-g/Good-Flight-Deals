"""Deciding whether a fare is a deal. Pure functions only — no I/O."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from flight_deals.models import Deal, Fare

_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}


@dataclass(frozen=True)
class DealRules:
    max_price: int
    min_drop_pct: float
    min_history: int


def format_price(amount: float, currency: str) -> str:
    symbol = _SYMBOLS.get(currency)
    return f"{symbol}{amount:,.0f}" if symbol else f"{amount:,.0f} {currency}"


def evaluate(fare: Fare, history: Sequence[int], rules: DealRules) -> Deal | None:
    """Return a Deal if `fare` beats its typical price or the absolute ceiling.

    `history` is past prices to the same destination, excluding this fare.
    """
    typical = median(history) if len(history) >= rules.min_history else None

    if typical is not None:
        drop_pct = (typical - fare.price) / typical * 100
        if drop_pct >= rules.min_drop_pct:
            reason = f"{drop_pct:.0f}% below typical {format_price(typical, fare.currency)}"
            return Deal(fare, reason, typical)

    if fare.price <= rules.max_price:
        reason = f"{format_price(rules.max_price, fare.currency)} or less"
        return Deal(fare, reason, typical)

    return None
