from collections.abc import Sequence
from typing import Protocol, TextIO

from flight_deals.deals import format_price
from flight_deals.models import Deal


class Notifier(Protocol):
    def send(self, deals: Sequence[Deal]) -> None: ...


def format_deals(deals: Sequence[Deal]) -> str:
    lines = [f"{len(deals)} flight deal{'s' if len(deals) != 1 else ''} found:", ""]
    for deal in deals:
        f = deal.fare
        stops = "direct" if f.stops == 0 else f"{f.stops} stop(s)" if f.stops else "stops unknown"
        duration = f", {f.duration_min // 60}h{f.duration_min % 60:02d}" if f.duration_min else ""
        lines.append(
            f"{format_price(f.price, f.currency)}  {f.destination}, {f.country} ({f.airport})  "
            f"{f.outbound:%a %d %b} - {f.inbound:%a %d %b}  {f.airline or 'airline unknown'}, "
            f"{stops}{duration}"
        )
        lines.append(f"    {deal.reason}")
        if f.link:
            lines.append(f"    {f.link}")
    return "\n".join(lines)


class ConsoleNotifier:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def send(self, deals: Sequence[Deal]) -> None:
        print(format_deals(deals), file=self._stream)
