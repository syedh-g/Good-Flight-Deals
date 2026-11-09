"""SerpApi (Google Travel Explore) flight source."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlencode

from flight_deals.models import Fare, Region, SearchSpec, TripLength
from flight_deals.sources.base import SourceError

ENDPOINT = "https://serpapi.com/search.json"

# Google Knowledge Graph ids for `arrival_area_id`, each checked against a live search.
_REGION_IDS = {
    Region.EUROPE: "/m/02j9z",
    Region.ASIA: "/m/0j0k",
    Region.NORTH_AMERICA: "/m/059g4",
    Region.SOUTH_AMERICA: "/m/06n3y",
    Region.AFRICA: "/m/0dg3n1",
    Region.CARIBBEAN: "/m/0261m",
}

_TRAVEL_DURATION = {
    TripLength.WEEKEND: "1",
    TripLength.ONE_WEEK: "2",
    TripLength.TWO_WEEKS: "3",
}

# SerpApi `stops`: 0 = any, 1 = nonstop, 2 = up to 1 stop, 3 = up to 2 stops.
_STOPS = {None: "0", 0: "1", 1: "2", 2: "3"}

HttpGet = Callable[[str, float], bytes]


def _urllib_get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


class SerpApiSource:
    name = "serpapi"

    def __init__(
        self,
        api_key: str,
        currency: str,
        *,
        http_get: HttpGet = _urllib_get,
        timeout: float = 60,
    ) -> None:
        self._api_key = api_key
        self._currency = currency
        self._http_get = http_get
        self._timeout = timeout

    def explore(self, origins: Sequence[str], spec: SearchSpec) -> list[Fare]:
        params = {
            "engine": "google_travel_explore",
            "departure_id": ",".join(origins),
            "travel_duration": _TRAVEL_DURATION[spec.trip_length],
            "stops": _STOPS[spec.max_stops],
            "currency": self._currency,
            "gl": "uk",
            "hl": "en",
        }
        if spec.region is not None:
            params["arrival_area_id"] = _REGION_IDS[spec.region]
        if spec.max_duration_min is not None:
            params["max_duration"] = str(spec.max_duration_min)
        return parse_explore(self._request(params), self._currency)

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        url = f"{ENDPOINT}?{urlencode({**params, 'api_key': self._api_key})}"
        try:
            body = self._http_get(url, self._timeout)
        except urllib.error.HTTPError as e:
            # SerpApi puts the useful message in a JSON body; never echo the URL (it holds the key).
            raise SourceError(f"SerpApi HTTP {e.code}: {_error_message(e.read())}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise SourceError(f"SerpApi unreachable: {e}") from None

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise SourceError(f"SerpApi returned invalid JSON: {e}") from None
        if "error" in data:
            raise SourceError(f"SerpApi error: {data['error']}")
        return data


def _error_message(body: bytes) -> str:
    try:
        return str(json.loads(body)["error"])
    except (ValueError, KeyError, TypeError):
        return body.decode(errors="replace")[:200]


def parse_explore(payload: dict[str, Any], currency: str) -> list[Fare]:
    """Convert a Travel Explore response into fares, skipping destinations without a price."""
    fares = []
    for d in payload.get("destinations", []):
        airport = (d.get("destination_airport") or {}).get("code")
        price = d.get("flight_price")
        if not airport or price is None or not d.get("start_date") or not d.get("end_date"):
            continue
        fares.append(
            Fare(
                destination=d.get("name", airport),
                country=d.get("country", ""),
                airport=airport,
                price=int(price),
                currency=currency,
                outbound=date.fromisoformat(d["start_date"]),
                inbound=date.fromisoformat(d["end_date"]),
                airline=d.get("airline"),
                stops=d.get("number_of_stops"),
                duration_min=d.get("flight_duration"),
                link=d.get("link"),
            )
        )
    return fares
