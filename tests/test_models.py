import pytest
from conftest import make_fare, make_spec


@pytest.mark.parametrize(
    ("stops", "accepted"),
    [(0, True), (1, True), (2, False), (None, False)],
)
def test_max_stops(stops, accepted):
    assert make_spec(max_stops=1).accepts(make_fare(stops=stops)) is accepted


@pytest.mark.parametrize(
    ("duration", "accepted"),
    [(255, False), (300, True), (1440, True), (1880, False), (None, False)],
)
def test_flight_duration_window(duration, accepted):
    spec = make_spec(min_duration_min=300, max_duration_min=1440)
    assert spec.accepts(make_fare(duration_min=duration)) is accepted


def test_no_filters_accepts_anything():
    assert make_spec().accepts(make_fare(stops=None, duration_min=None))
