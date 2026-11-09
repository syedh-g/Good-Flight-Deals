import io
import json
import urllib.error
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import make_spec

from flight_deals.models import Region, TripLength
from flight_deals.sources import SourceError
from flight_deals.sources.serpapi import SerpApiSource, parse_explore

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str = "serpapi_explore.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_real_response_skips_unpriced_destinations():
    fares = parse_explore(load_fixture(), "GBP")

    assert len(fares) == 43
    cork = next(f for f in fares if f.airport == "ORK")
    assert cork.price == 32
    assert cork.currency == "GBP"
    assert cork.outbound == date(2026, 11, 16)
    assert cork.inbound == date(2026, 11, 24)
    assert cork.stops == 0
    assert cork.airline == "Ryanair"


def test_parse_long_haul_response():
    fares = parse_explore(load_fixture("serpapi_explore_asia.json"), "GBP")

    bangkok = next(f for f in fares if f.airport == "BKK")
    assert bangkok.price == 438
    assert bangkok.stops == 1
    assert bangkok.duration_min == 895


def capture_query(spec, origins=("LHR", "MAN")) -> dict[str, list[str]]:
    seen = {}

    def fake_get(url, timeout):
        seen["query"] = parse_qs(urlparse(url).query)
        return json.dumps(load_fixture()).encode()

    SerpApiSource("secret", "GBP", http_get=fake_get).explore(list(origins), spec)
    return seen["query"]


def test_default_spec_query():
    q = capture_query(make_spec())

    assert q["engine"] == ["google_travel_explore"]
    assert q["departure_id"] == ["LHR,MAN"]
    assert q["currency"] == ["GBP"]
    assert q["api_key"] == ["secret"]
    assert q["stops"] == ["0"]
    assert q["travel_duration"] == ["2"]
    assert "arrival_area_id" not in q
    assert "max_duration" not in q


def test_long_haul_spec_query():
    spec = make_spec(
        region=Region.ASIA,
        trip_length=TripLength.TWO_WEEKS,
        max_stops=1,
        min_duration_min=300,
        max_duration_min=1440,
    )
    q = capture_query(spec)

    assert q["arrival_area_id"] == ["/m/0j0k"]
    assert q["travel_duration"] == ["3"]
    assert q["stops"] == ["2"]  # SerpApi's code for "1 stop or fewer"
    assert q["max_duration"] == ["1440"]


def test_api_error_in_body_raises():
    source = SerpApiSource("k", "GBP", http_get=lambda url, t: b'{"error": "Invalid API key."}')
    with pytest.raises(SourceError, match="Invalid API key"):
        source.explore(["LHR"], make_spec())


def test_http_error_message_does_not_leak_key():
    def fail(url, timeout):
        body = io.BytesIO(b'{"error": "Your account has run out of searches."}')
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, body)

    with pytest.raises(SourceError) as exc:
        SerpApiSource("super-secret", "GBP", http_get=fail).explore(["LHR"], make_spec())

    assert "run out of searches" in str(exc.value)
    assert "super-secret" not in str(exc.value)
    assert exc.value.__cause__ is None
