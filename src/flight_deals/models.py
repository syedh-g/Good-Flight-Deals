from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Fare:
    """Cheapest return fare found to one destination airport."""

    destination: str
    country: str
    airport: str
    price: int
    currency: str
    outbound: date
    inbound: date
    airline: str | None
    stops: int | None
    duration_min: int | None
    link: str | None


@dataclass(frozen=True)
class Deal:
    fare: Fare
    reason: str
    typical_price: float | None
