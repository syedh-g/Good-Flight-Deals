from pathlib import Path

import pytest

from flight_deals.config import ConfigError, load_api_key, load_config
from flight_deals.models import Region, TripLength

REPO_CONFIG = Path(__file__).parent.parent / "config.toml"

BASE = """
[search]
origins = ["LHR"]
currency = "GBP"

[deals]
min_zscore = 2.0
min_saving_pct = 12
min_history_days = 7
min_spread_pct = 5
history_days = 60
alert_cooldown_days = 14

[budget]
monthly_search_limit = 240
"""


def write_config(tmp_path: Path, searches: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(BASE + searches, encoding="utf-8")
    return path


def test_repo_config_loads():
    config = load_config(REPO_CONFIG)
    assert config.origins == ("LHR", "LGW", "STN", "LTN", "BHX", "MAN")
    assert config.currency == "GBP"
    assert config.db_path == REPO_CONFIG.parent / "data" / "flight_deals.db"
    assert len(config.searches) * 31 <= config.monthly_search_limit

    asia = next(s for s in config.searches if s.name == "asia")
    assert asia.region is Region.ASIA
    assert asia.trip_length is TripLength.TWO_WEEKS
    assert asia.max_stops == 1
    assert (asia.min_duration_min, asia.max_duration_min) == (240, 1440)
    assert asia.max_price is None
    assert next(s for s in config.searches if s.name == "europe").max_price == 30


def test_search_defaults(tmp_path):
    config = load_config(write_config(tmp_path, '[[searches]]\nname = "anywhere"\n'))
    (spec,) = config.searches
    assert spec.region is None
    assert spec.trip_length is TripLength.ONE_WEEK
    assert spec.max_stops is None
    assert spec.min_duration_min is None


@pytest.mark.parametrize(
    ("searches", "message"),
    [
        ("", "at least one"),
        ('[[searches]]\nname = "Bad Name"\n', "search name"),
        ('[[searches]]\nname = "x"\nregion = "atlantis"\n', "atlantis"),
        ('[[searches]]\nname = "x"\ntrip_length = "month"\n', "month"),
        ('[[searches]]\nname = "x"\nmax_stops = 3\n', "max_stops"),
        ('[[searches]]\nname = "x"\nmin_flight_hours = -1\n', "min_flight_hours"),
        (
            '[[searches]]\nname = "x"\nmin_flight_hours = 10\nmax_flight_hours = 5\n',
            "below max_flight_hours",
        ),
        ('[[searches]]\nname = "x"\n[[searches]]\nname = "x"\n', "unique"),
    ],
)
def test_invalid_searches_rejected(tmp_path, searches, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, searches))


def test_invalid_origin_rejected(tmp_path):
    text = REPO_CONFIG.read_text(encoding="utf-8").replace('"LHR"', '"heathrow"')
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="origins"):
        load_config(path)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("max_price = 30", "max_price = -1", "max_price"),
        ("min_zscore = 2.0", "min_zscore = 0", "min_zscore"),
        ("min_saving_pct = 12", "min_saving_pct = 100", "min_saving_pct"),
        ("min_history_days = 7", "min_history_days = 7.5", "whole numbers"),
        ("min_history_days = 7", "min_history_days = 90", "more than history_days"),
    ],
)
def test_invalid_deal_settings_rejected(tmp_path, old, new, message):
    text = REPO_CONFIG.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "config.toml"
    path.write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_api_key_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SERPAPI_API_KEY=from-file\n", encoding="utf-8")
    assert load_api_key(env_file, {"SERPAPI_API_KEY": "from-env"}) == "from-env"
    assert load_api_key(env_file, {}) == "from-file"


def test_api_key_quotes_and_comments_handled(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nSERPAPI_API_KEY="abc123"\n', encoding="utf-8")
    assert load_api_key(env_file, {}) == "abc123"


def test_missing_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SERPAPI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="SERPAPI_API_KEY"):
        load_api_key(env_file, {})
