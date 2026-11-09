import math

import pytest
from conftest import make_fare

from flight_deals.deals import DealRules, assess, build_baseline, format_price

RULES = DealRules(min_zscore=2.0, min_saving_pct=12, min_history_days=7, min_spread_pct=5)

VOLATILE = [30, 38, 42, 45, 55, 60, 70]  # e.g. Ryanair to Barcelona
STABLE = [430, 435, 438, 440, 442, 445, 450]  # e.g. Gulf Air to Bangkok


def test_no_baseline_until_enough_days():
    assert build_baseline([100] * 6, RULES) is None
    assert build_baseline([100] * 7, RULES) is not None


def test_baseline_is_robust_to_a_glitch_price():
    clean = build_baseline([100, 102, 98, 101, 99, 100, 103], RULES)
    glitched = build_baseline([100, 102, 98, 101, 99, 100, 5000], RULES)
    assert clean is not None and glitched is not None
    assert glitched.typical == pytest.approx(clean.typical, rel=0.02)
    assert glitched.spread == pytest.approx(clean.spread, rel=0.5)


def test_flat_route_uses_spread_floor():
    baseline = build_baseline([440] * 10, RULES)
    assert baseline is not None
    assert baseline.spread == pytest.approx(0.05)


def test_routine_low_on_volatile_route_is_not_a_deal():
    a = assess(make_fare(price=33), VOLATILE, RULES, max_price=None)
    assert a.zscore == pytest.approx(-1.04, abs=0.01)
    assert a.deal is None


def test_modest_drop_on_stable_route_is_a_deal():
    a = assess(make_fare(price=380), STABLE, RULES, max_price=None)
    assert a.zscore is not None and a.zscore < -2
    assert a.deal is not None
    assert a.deal.typical_price == pytest.approx(440)
    assert a.deal.reason.startswith("usually £440 (normally £")
    assert "14% off" in a.deal.reason
    assert a.deal.reason.endswith("lowest in 7 days tracked")


def test_unusual_but_too_small_saving_is_not_a_deal():
    # Flat route: 10% below is over 2 spreads out but under the 12% minimum saving.
    a = assess(make_fare(price=395), [440] * 10, RULES, max_price=None)
    assert a.zscore is not None and a.zscore < -RULES.min_zscore
    assert a.deal is None


def test_price_above_typical_scores_positive():
    a = assess(make_fare(price=500), STABLE, RULES, max_price=None)
    assert a.zscore is not None and a.zscore > 0
    assert a.deal is None


def test_ceiling_applies_without_history():
    a = assess(make_fare(price=29), [], RULES, max_price=30)
    assert a.baseline is None and a.zscore is None
    assert a.deal is not None
    assert a.deal.reason == "£30 or less"


def test_anomaly_reason_preferred_over_ceiling():
    a = assess(make_fare(price=20), [40] * 7, RULES, max_price=30)
    assert a.deal is not None
    assert a.deal.reason.startswith("usually £40")


def test_not_lowest_when_history_had_cheaper_day():
    history = [440] * 6 + [370]
    a = assess(make_fare(price=380), history, RULES, max_price=None)
    assert a.deal is not None
    assert "lowest" not in a.deal.reason


def test_zscore_matches_definition():
    baseline = build_baseline(STABLE, RULES)
    assert baseline is not None
    expected = (math.log(380) - math.log(baseline.typical)) / baseline.spread
    assert baseline.zscore(380) == pytest.approx(expected)


def test_format_price_unknown_currency():
    assert format_price(1234, "SEK") == "1,234 SEK"
