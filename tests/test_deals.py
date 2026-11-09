from conftest import make_fare

from flight_deals.deals import DealRules, evaluate, format_price

RULES = DealRules(max_price=40, min_drop_pct=25, min_history=5)


def test_cheap_fare_without_history_is_a_deal():
    deal = evaluate(make_fare(price=35), [], RULES)
    assert deal is not None
    assert deal.reason == "£40 or less"
    assert deal.typical_price is None


def test_expensive_fare_without_enough_history_is_not_a_deal():
    assert evaluate(make_fare(price=60), [100, 100, 100, 100], RULES) is None


def test_fare_well_below_typical_is_a_deal():
    deal = evaluate(make_fare(price=60), [100, 90, 110, 100, 100], RULES)
    assert deal is not None
    assert deal.typical_price == 100
    assert deal.reason == "40% below typical £100"


def test_small_drop_is_not_a_deal():
    assert evaluate(make_fare(price=80), [100] * 5, RULES) is None


def test_format_price_unknown_currency():
    assert format_price(1234, "SEK") == "1,234 SEK"
