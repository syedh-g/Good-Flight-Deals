import io
import json
import urllib.error
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from flight_deals.sources import SourceError
from flight_deals.sources.serpapi import SerpApiSource, parse_explore

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_explore.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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


def test_explore_sends_expected_query():
    seen = {}

    def fake_get(url, timeout):
        seen["query"] = parse_qs(urlparse(url).query)
        return json.dumps(load_fixture()).encode()

    fares = SerpApiSource("secret", "GBP", http_get=fake_get).explore(["LHR", "MAN"])

    assert fares
    q = seen["query"]
    assert q["engine"] == ["google_travel_explore"]
    assert q["departure_id"] == ["LHR,MAN"]
    assert q["currency"] == ["GBP"]
    assert q["api_key"] == ["secret"]


def test_api_error_in_body_raises():
    source = SerpApiSource("k", "GBP", http_get=lambda url, t: b'{"error": "Invalid API key."}')
    with pytest.raises(SourceError, match="Invalid API key"):
        source.explore(["LHR"])


def test_http_error_message_does_not_leak_key():
    def fail(url, timeout):
        body = io.BytesIO(b'{"error": "Your account has run out of searches."}')
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, body)

    with pytest.raises(SourceError) as exc:
        SerpApiSource("super-secret", "GBP", http_get=fail).explore(["LHR"])

    assert "run out of searches" in str(exc.value)
    assert "super-secret" not in str(exc.value)
    assert exc.value.__cause__ is None
